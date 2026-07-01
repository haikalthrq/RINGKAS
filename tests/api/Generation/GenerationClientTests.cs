using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Ringkas.Api.Generation;

namespace Ringkas.Api.Tests.Generation;

public sealed class GenerationClientTests
{
    [Fact]
    public void RequestAndResultContractsRejectInvalidValuesAndRedactContent()
    {
        Assert.Throws<GenerationException>(() => new GenerationRequest([]));
        Assert.Throws<GenerationException>(() => new GenerationRequest([new GenerationMessage((GenerationRole)99, "text")]));
        Assert.Throws<GenerationException>(() => new GenerationRequest([new GenerationMessage(GenerationRole.User, " ")]));
        Assert.Throws<GenerationException>(() => new GenerationResult("", GenerationProvider.NvidiaNim, "model"));
        Assert.Throws<GenerationException>(() => new GenerationUsage(-1));

        var request = Request("prompt that must not render");
        var result = new GenerationResult("response that must not render", GenerationProvider.NvidiaNim, "model");
        Assert.DoesNotContain("prompt", request.ToString(), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("response", result.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task NvidiaSendsOpenAiCompatibleRequestAndParsesUsage()
    {
        HttpRequestMessage? captured = null;
        string? capturedBody = null;
        var handler = new DelegateHandler((request, _) =>
        {
            captured = request;
            capturedBody = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Response(HttpStatusCode.OK, """{"choices":[{"message":{"content":"answer"}}],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}""");
        });
        var client = new NvidiaNimGenerationClient(new HttpClient(handler), Configuration());

        var result = await client.GenerateAsync(Request("private prompt"));

        Assert.NotNull(captured);
        Assert.Equal(HttpMethod.Post, captured!.Method);
        Assert.Equal("https://nim.example/v1/chat/completions", captured.RequestUri!.ToString());
        Assert.Equal("Bearer", captured.Headers.Authorization!.Scheme);
        Assert.Equal("nvidia-secret", captured.Headers.Authorization.Parameter);
        using var json = JsonDocument.Parse(capturedBody!);
        Assert.Equal("nvidia-model", json.RootElement.GetProperty("model").GetString());
        Assert.False(json.RootElement.GetProperty("stream").GetBoolean());
        Assert.Equal("user", json.RootElement.GetProperty("messages")[0].GetProperty("role").GetString());
        Assert.Equal("private prompt", json.RootElement.GetProperty("messages")[0].GetProperty("content").GetString());
        Assert.Equal(GenerationProvider.NvidiaNim, result.Provider);
        Assert.Equal("answer", result.Text);
        Assert.Equal(5, result.Usage!.TotalTokens);
    }

    [Theory]
    [InlineData(400, GenerationFailureCategory.ProviderRejection)]
    [InlineData(401, GenerationFailureCategory.AuthenticationOrAuthorization)]
    [InlineData(403, GenerationFailureCategory.AuthenticationOrAuthorization)]
    [InlineData(408, GenerationFailureCategory.Timeout)]
    [InlineData(422, GenerationFailureCategory.ProviderRejection)]
    [InlineData(429, GenerationFailureCategory.RateLimited)]
    [InlineData(500, GenerationFailureCategory.ProviderRejection)]
    public async Task NvidiaClassifiesHttpFailures(int statusCode, GenerationFailureCategory expected)
    {
        var client = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) => Response((HttpStatusCode)statusCode, "provider-body-secret"))), Configuration());
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request("prompt-secret")));
        Assert.Equal(expected, error.Category);
        Assert.Equal(statusCode, error.StatusCode);
        Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("not-a-url")]
    [InlineData("http://nim.example/v1")]
    [InlineData("https://user:password@nim.example/v1")]
    [InlineData("https://nim.example/v1?token=secret")]
    public async Task NvidiaRejectsUnsafeBaseUrlBeforeHttpInvocation(string baseUrl)
    {
        var calls = 0;
        var client = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
        {
            calls++;
            throw new InvalidOperationException();
        })), Configuration(nvidiaBaseUrl: baseUrl));
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request()));
        Assert.Equal(GenerationFailureCategory.InvalidConfiguration, error.Category);
        Assert.Equal(0, calls);
        Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task NvidiaClassifiesTransportTimeoutAndPropagatesCallerCancellation()
    {
        var transport = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) => throw new HttpRequestException())), Configuration());
        var transportError = await Assert.ThrowsAsync<GenerationException>(() => transport.GenerateAsync(Request()));
        Assert.Equal(GenerationFailureCategory.TransportUnavailable, transportError.Category);

        var timeout = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
            Task.FromException<HttpResponseMessage>(new OperationCanceledException()))), Configuration());
        var timeoutError = await Assert.ThrowsAsync<GenerationException>(() => timeout.GenerateAsync(Request()));
        Assert.Equal(GenerationFailureCategory.Timeout, timeoutError.Category);

        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => transport.GenerateAsync(Request(), cancelled.Token));
    }

    [Theory]
    [InlineData("integrate.api.nvidia.com", "https://integrate.api.nvidia.com/v1/", true)]
    [InlineData("nim.internal.example:8443", "https://nim.internal.example:8443/v1", true)]
    [InlineData("integrate.api.nvidia.com", "https://lookalike.integrate.api.nvidia.com/v1", false)]
    [InlineData("nim.internal.example:8443", "https://nim.internal.example/v1", false)]
    [InlineData("127.0.0.1", "https://127.0.0.1/v1", true)]
    [InlineData("integrate.api.nvidia.com", "https://127.0.0.1/v1", false)]
    public async Task NvidiaRequiresExactAllowedAuthority(string allowedHosts, string baseUrl, bool shouldSucceed)
    {
        var calls = 0;
        var client = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
        {
            calls++;
            return Response(HttpStatusCode.OK, """{"choices":[{"message":{"content":"answer"}}]}""");
        })), Configuration(nvidiaBaseUrl: baseUrl, allowedHosts: allowedHosts));

        if (shouldSucceed)
        {
            await client.GenerateAsync(Request());
            Assert.Equal(1, calls);
        }
        else
        {
            var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request()));
            Assert.Equal(GenerationFailureCategory.InvalidConfiguration, error.Category);
            Assert.Equal(0, calls);
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData("nim.example,")]
    [InlineData("nim.example,nim.example")]
    [InlineData("*.example.com")]
    [InlineData("https://nim.example")]
    public async Task NvidiaRejectsMalformedAllowedAuthorities(string allowedHosts)
    {
        var calls = 0;
        var client = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
        {
            calls++;
            throw new InvalidOperationException();
        })), Configuration(allowedHosts: allowedHosts));
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request()));
        Assert.Equal(GenerationFailureCategory.InvalidConfiguration, error.Category);
        Assert.Equal(0, calls);
    }

    [Theory]
    [InlineData("0")]
    [InlineData("-1")]
    [InlineData("0.5")]
    [InlineData("301")]
    [InlineData("NaN")]
    [InlineData("Infinity")]
    [InlineData("999999999999999999999999")]
    public async Task ProviderTimeoutMustBeBetweenOneAndThreeHundredSeconds(string timeout)
    {
        var nvidia = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) => throw new InvalidOperationException())), Configuration(timeout: timeout));
        var cloudflare = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) => throw new InvalidOperationException())), Configuration(cloudflareTimeout: timeout));
        Assert.Equal(GenerationFailureCategory.InvalidConfiguration, (await Assert.ThrowsAsync<GenerationException>(() => nvidia.GenerateAsync(Request()))).Category);
        Assert.Equal(GenerationFailureCategory.InvalidConfiguration, (await Assert.ThrowsAsync<GenerationException>(() => cloudflare.GenerateAsync(Request()))).Category);
    }

    [Fact]
    public async Task NvidiaRejectsMalformedResponsesWithoutLeakingBody()
    {
        foreach (var body in new[] { "not-json-secret", "{}", "{\"choices\":[{\"message\":{\"content\":\" \"}}]}" })
        {
            var client = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((_, _) => Response(HttpStatusCode.OK, body))), Configuration());
            var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request("prompt-secret")));
            Assert.Equal(GenerationFailureCategory.MalformedResponse, error.Category);
            Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public async Task CloudflareUsesAccountScopedOpenAiEndpointAndConfiguredModel()
    {
        HttpRequestMessage? captured = null;
        string? capturedBody = null;
        var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((request, _) =>
        {
            captured = request;
            capturedBody = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return Response(HttpStatusCode.OK, """{"choices":[{"message":{"content":"fallback answer"}}]}""");
        })), Configuration());

        var result = await client.GenerateAsync(Request());

        Assert.Equal("https://api.cloudflare.com/client/v4/accounts/account_123/ai/v1/chat/completions", captured!.RequestUri!.ToString());
        Assert.Equal("cloudflare-secret", captured.Headers.Authorization!.Parameter);
        using var json = JsonDocument.Parse(capturedBody!);
        Assert.Equal("cloudflare-model", json.RootElement.GetProperty("model").GetString());
        Assert.False(json.RootElement.GetProperty("stream").GetBoolean());
        Assert.Equal(GenerationProvider.CloudflareWorkersAi, result.Provider);
    }

    [Theory]
    [InlineData("account/id")]
    [InlineData("")]
    [InlineData("account id")]
    [InlineData("../account")]
    [InlineData("account?query")]
    [InlineData("account%2Fid")]
    public async Task CloudflareRejectsUnsafeAccountId(string accountId)
    {
        var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) => throw new InvalidOperationException())), Configuration(accountId: accountId));
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request()));
        Assert.Equal(GenerationFailureCategory.InvalidConfiguration, error.Category);
    }

    [Fact]
    public async Task CloudflareRejectsMissingOversizedAndUnsafeConfigurationWithoutHttpInvocation()
    {
        foreach (var configuration in new[]
        {
            Configuration(includeCloudflare: false),
            Configuration(accountId: new string('a', 129)),
            Configuration(cloudflareToken: " "),
            Configuration(cloudflareModel: " ")
        })
        {
            var calls = 0;
            var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
            {
                calls++;
                throw new InvalidOperationException();
            })), configuration);
            var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request("prompt-secret")));
            Assert.Equal(GenerationFailureCategory.InvalidConfiguration, error.Category);
            Assert.Equal(0, calls);
            Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
        }
    }

    [Theory]
    [InlineData(400, GenerationFailureCategory.ProviderRejection)]
    [InlineData(401, GenerationFailureCategory.AuthenticationOrAuthorization)]
    [InlineData(403, GenerationFailureCategory.AuthenticationOrAuthorization)]
    [InlineData(408, GenerationFailureCategory.Timeout)]
    [InlineData(422, GenerationFailureCategory.ProviderRejection)]
    [InlineData(429, GenerationFailureCategory.RateLimited)]
    [InlineData(503, GenerationFailureCategory.ProviderRejection)]
    public async Task CloudflareClassifiesHttpFailuresWithoutLeakingResponse(int statusCode, GenerationFailureCategory expected)
    {
        var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) => Response((HttpStatusCode)statusCode, "raw-response-secret"))), Configuration());
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request("prompt-secret")));
        Assert.Equal(expected, error.Category);
        Assert.Equal(statusCode, error.StatusCode);
        Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CloudflareClassifiesTransportAndTimeoutAndPropagatesCallerCancellation()
    {
        var transport = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) => throw new HttpRequestException())), Configuration());
        Assert.Equal(GenerationFailureCategory.TransportUnavailable, (await Assert.ThrowsAsync<GenerationException>(() => transport.GenerateAsync(Request()))).Category);

        var timeout = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
            Task.FromException<HttpResponseMessage>(new OperationCanceledException()))), Configuration());
        Assert.Equal(GenerationFailureCategory.Timeout, (await Assert.ThrowsAsync<GenerationException>(() => timeout.GenerateAsync(Request()))).Category);

        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => transport.GenerateAsync(Request(), cancelled.Token));
    }

    [Theory]
    [InlineData("not-json-secret")]
    [InlineData("{}")]
    [InlineData("{\"choices\":null}")]
    [InlineData("{\"choices\":[]}")]
    [InlineData("{\"choices\":[null]}")]
    [InlineData("{\"choices\":[{\"message\":null}]}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":12}}]}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":\" \"}}]}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":\"x\"}}],\"usage\":null}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":\"x\"}}],\"usage\":{\"total_tokens\":-1}}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":\"x\"}}],\"usage\":{\"total_tokens\":1.5}}")]
    [InlineData("{\"choices\":[{\"message\":{\"content\":\"x\"}}],\"usage\":{\"total_tokens\":999999999999}}")]
    public async Task ParserRejectsMalformedOpenAiResponseBoundaries(string body)
    {
        var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) => Response(HttpStatusCode.OK, body))), Configuration());
        var error = await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request("prompt-secret")));
        Assert.Equal(GenerationFailureCategory.MalformedResponse, error.Category);
        Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParserUsesTheFirstChoice()
    {
        var client = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((_, _) =>
            Response(HttpStatusCode.OK, """{"choices":[{"message":{"content":"first"}},{"message":{"content":"second"}}]}"""))), Configuration());
        var result = await client.GenerateAsync(Request());
        Assert.Equal("first", result.Text);
    }

    [Fact]
    public async Task FailoverMakesAtMostOneLocalFallbackInvocationForEligiblePrimaryFailure()
    {
        var primary = new ScriptedNvidiaClient(_ => throw new GenerationException(GenerationFailureCategory.RateLimited, "safe", 429));
        var fallback = new ScriptedCloudflareClient(_ => Task.FromResult(new GenerationResult("answer", GenerationProvider.CloudflareWorkersAi, "fallback-model")));
        var client = new FailoverGenerationClient(primary, fallback, new ListLogger());

        var result = await client.GenerateAsync(Request());

        Assert.Equal(1, primary.Calls);
        Assert.Equal(1, fallback.Calls);
        Assert.Equal(GenerationProvider.CloudflareWorkersAi, result.Provider);
    }

    [Fact]
    public async Task FailoverDoesNotInvokeFallbackAfterPrimarySuccess()
    {
        var primary = new ScriptedNvidiaClient(_ => Task.FromResult(new GenerationResult("answer", GenerationProvider.NvidiaNim, "model")));
        var fallback = new ScriptedCloudflareClient(_ => throw new InvalidOperationException());
        var result = await new FailoverGenerationClient(primary, fallback, new ListLogger()).GenerateAsync(Request());
        Assert.Equal(GenerationProvider.NvidiaNim, result.Provider);
        Assert.Equal(0, fallback.Calls);
    }

    [Theory]
    [InlineData(GenerationFailureCategory.TransportUnavailable, 0)]
    [InlineData(GenerationFailureCategory.Timeout, 0)]
    [InlineData(GenerationFailureCategory.Timeout, 408)]
    [InlineData(GenerationFailureCategory.RateLimited, 429)]
    [InlineData(GenerationFailureCategory.ProviderRejection, 500)]
    [InlineData(GenerationFailureCategory.ProviderRejection, 502)]
    [InlineData(GenerationFailureCategory.ProviderRejection, 503)]
    [InlineData(GenerationFailureCategory.MalformedResponse, 0)]
    public async Task FailoverInvokesFallbackOnceForEligiblePrimaryFailure(GenerationFailureCategory category, int statusCode)
    {
        var primary = new ScriptedNvidiaClient(_ => throw new GenerationException(category, "raw-primary-secret", statusCode == 0 ? null : statusCode));
        var fallback = new ScriptedCloudflareClient(_ => Task.FromResult(new GenerationResult("answer", GenerationProvider.CloudflareWorkersAi, "model")));
        var result = await new FailoverGenerationClient(primary, fallback, new ListLogger()).GenerateAsync(Request());
        Assert.Equal(GenerationProvider.CloudflareWorkersAi, result.Provider);
        Assert.Equal(1, fallback.Calls);
    }

    [Theory]
    [InlineData(GenerationFailureCategory.InvalidRequest, 0)]
    [InlineData(GenerationFailureCategory.InvalidConfiguration, 0)]
    [InlineData(GenerationFailureCategory.AuthenticationOrAuthorization, 401)]
    [InlineData(GenerationFailureCategory.ProviderRejection, 400)]
    public async Task FailoverDoesNotRunForIneligiblePrimaryFailures(GenerationFailureCategory category, int statusCode)
    {
        var primary = new ScriptedNvidiaClient(_ => throw new GenerationException(category, "safe", statusCode == 0 ? null : statusCode));
        var fallback = new ScriptedCloudflareClient(_ => throw new InvalidOperationException());
        var client = new FailoverGenerationClient(primary, fallback, new ListLogger());

        await Assert.ThrowsAsync<GenerationException>(() => client.GenerateAsync(Request()));
        Assert.Equal(0, fallback.Calls);
    }

    [Fact]
    public async Task FailoverReturnsSanitizedExhaustedErrorWithoutInnerException()
    {
        var primary = new ScriptedNvidiaClient(_ => throw new GenerationException(GenerationFailureCategory.MalformedResponse, "raw-primary-secret"));
        var fallback = new ScriptedCloudflareClient(_ => throw new GenerationException(GenerationFailureCategory.AuthenticationOrAuthorization, "raw-fallback-secret"));
        var error = await Assert.ThrowsAsync<GenerationFallbackExhaustedException>(() => new FailoverGenerationClient(primary, fallback, new ListLogger()).GenerateAsync(Request()));

        Assert.Null(error.InnerException);
        Assert.Equal(GenerationFailureCategory.MalformedResponse, error.PrimaryFailure);
        Assert.Equal(GenerationFailureCategory.AuthenticationOrAuthorization, error.FallbackFailure);
        Assert.DoesNotContain("secret", error.ToString(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task FailoverDoesNotInvokeFallbackWhenCancellationOccursBeforeOrBetweenAttempts()
    {
        using var beforePrimary = new CancellationTokenSource();
        beforePrimary.Cancel();
        var primary = new ScriptedNvidiaClient(_ => throw new InvalidOperationException());
        var fallback = new ScriptedCloudflareClient(_ => throw new InvalidOperationException());
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new FailoverGenerationClient(primary, fallback, new ListLogger()).GenerateAsync(Request(), beforePrimary.Token));
        Assert.Equal(0, fallback.Calls);

        using var betweenAttempts = new CancellationTokenSource();
        var cancellingPrimary = new ScriptedNvidiaClient(_ =>
        {
            betweenAttempts.Cancel();
            throw new GenerationException(GenerationFailureCategory.Timeout, "raw-primary-secret");
        });
        var secondFallback = new ScriptedCloudflareClient(_ => throw new InvalidOperationException());
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new FailoverGenerationClient(cancellingPrimary, secondFallback, new ListLogger()).GenerateAsync(Request(), betweenAttempts.Token));
        Assert.Equal(0, secondFallback.Calls);
    }

    [Fact]
    public async Task FailoverLogsOnlySafeMetadata()
    {
        var logger = new ListLogger();
        var primary = new ScriptedNvidiaClient(_ => throw new GenerationException(GenerationFailureCategory.RateLimited, "prompt-response-model-url-account-token", 429));
        var fallback = new ScriptedCloudflareClient(_ => Task.FromResult(new GenerationResult("response-secret", GenerationProvider.CloudflareWorkersAi, "model-secret")));
        await new FailoverGenerationClient(primary, fallback, logger).GenerateAsync(Request("prompt-secret"));

        var output = string.Join('\n', logger.Messages);
        Assert.Contains(nameof(GenerationFailureCategory.RateLimited), output);
        Assert.Contains(nameof(GenerationProvider.CloudflareWorkersAi), output);
        foreach (var secret in new[] { "prompt", "response", "model", "url", "account", "token" })
        {
            Assert.DoesNotContain(secret, output, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public async Task FailoverUsesTheLockedFiveModelOrder()
    {
        var nvidiaModels = new List<string>();
        var cloudflareModels = new List<string>();
        var nvidiaResponses = new Queue<HttpResponseMessage>([
            ResponseMessage(HttpStatusCode.InternalServerError, "nvidia-primary-failure"),
            ResponseMessage(HttpStatusCode.InternalServerError, "nvidia-secondary-failure"),
            ResponseMessage(HttpStatusCode.InternalServerError, "nvidia-lightweight-failure")
        ]);
        var cloudflareResponses = new Queue<HttpResponseMessage>([
            ResponseMessage(HttpStatusCode.InternalServerError, "cloudflare-fallback-failure"),
            ResponseMessage(HttpStatusCode.OK, """{"choices":[{"message":{"content":"experimental answer"}}]}""")
        ]);
        var configuration = Configuration(
            secondaryModel: "mistral-model",
            lightweightModel: "mini-model",
            experimentalModel: "llama4-model");
        var primary = new NvidiaNimGenerationClient(new HttpClient(new DelegateHandler((request, _) =>
        {
            nvidiaModels.Add(JsonDocument.Parse(request.Content!.ReadAsStringAsync().GetAwaiter().GetResult()).RootElement.GetProperty("model").GetString()!);
            return Task.FromResult(nvidiaResponses.Dequeue());
        })), configuration);
        var fallback = new CloudflareWorkersAiGenerationClient(new HttpClient(new DelegateHandler((request, _) =>
        {
            cloudflareModels.Add(JsonDocument.Parse(request.Content!.ReadAsStringAsync().GetAwaiter().GetResult()).RootElement.GetProperty("model").GetString()!);
            return Task.FromResult(cloudflareResponses.Dequeue());
        })), configuration);

        var result = await new FailoverGenerationClient(primary, fallback, new ListLogger(), configuration).GenerateAsync(Request());

        Assert.Equal(GenerationProvider.CloudflareWorkersAi, result.Provider);
        Assert.Equal("llama4-model", result.Model);
        Assert.Equal(["nvidia-model", "mistral-model", "mini-model"], nvidiaModels);
        Assert.Equal(["cloudflare-model", "llama4-model"], cloudflareModels);
    }

    [Fact]
    public void DependencyInjectionResolvesWithoutFallbackConfigurationOrNetwork()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(Configuration(includeCloudflare: false));
        services.AddLogging();
        services.AddGenerationClients();
        using var provider = services.BuildServiceProvider();

        Assert.IsType<FailoverGenerationClient>(provider.GetRequiredService<IGenerationClient>());
    }

    private static GenerationRequest Request(string content = "hello") => new([new GenerationMessage(GenerationRole.User, content)]);

    private static IConfiguration Configuration(
        string? nvidiaBaseUrl = null,
        string? timeout = null,
        string? accountId = null,
        bool includeCloudflare = true,
        string? allowedHosts = null,
        string? cloudflareToken = null,
        string? cloudflareModel = null,
        string? cloudflareTimeout = null,
        string? secondaryModel = null,
        string? lightweightModel = null,
        string? experimentalModel = null) =>
        new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["NVIDIA_NIM_API_KEY"] = "nvidia-secret",
            ["NVIDIA_NIM_GENERATION_MODEL"] = "nvidia-model",
            ["NVIDIA_NIM_GENERATION_BASE_URL"] = nvidiaBaseUrl ?? "https://nim.example/v1/",
            ["NVIDIA_NIM_GENERATION_TIMEOUT_SECONDS"] = timeout ?? "10",
            ["NVIDIA_NIM_GENERATION_ALLOWED_HOSTS"] = allowedHosts ?? "nim.example",
            ["CLOUDFLARE_ACCOUNT_ID"] = includeCloudflare ? accountId ?? "account_123" : null,
            ["CLOUDFLARE_API_TOKEN"] = includeCloudflare ? cloudflareToken ?? "cloudflare-secret" : null,
            ["CLOUDFLARE_WORKERS_AI_GENERATION_MODEL"] = includeCloudflare ? cloudflareModel ?? "cloudflare-model" : null,
            ["CLOUDFLARE_WORKERS_AI_GENERATION_TIMEOUT_SECONDS"] = includeCloudflare ? cloudflareTimeout ?? "10" : null,
            ["NVIDIA_NIM_GENERATION_SECONDARY_MODEL"] = secondaryModel,
            ["NVIDIA_NIM_GENERATION_LIGHTWEIGHT_MODEL"] = lightweightModel,
            ["CLOUDFLARE_WORKERS_AI_EXPERIMENTAL_MODEL"] = experimentalModel
        }).Build();

    private static Task<HttpResponseMessage> Response(HttpStatusCode statusCode, string body) =>
        Task.FromResult(ResponseMessage(statusCode, body));

    private static HttpResponseMessage ResponseMessage(HttpStatusCode statusCode, string body) =>
        new(statusCode) { Content = new StringContent(body, Encoding.UTF8, "application/json") };

    private sealed class DelegateHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
    }

    private abstract class ScriptedClient(Func<GenerationRequest, Task<GenerationResult>> generate) : IGenerationClient
    {
        public int Calls { get; private set; }

        public Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
        {
            Calls++;
            cancellationToken.ThrowIfCancellationRequested();
            return generate(request);
        }
    }

    private sealed class ScriptedNvidiaClient(Func<GenerationRequest, Task<GenerationResult>> generate) : ScriptedClient(generate), INvidiaNimGenerationClient;

    private sealed class ScriptedCloudflareClient(Func<GenerationRequest, Task<GenerationResult>> generate) : ScriptedClient(generate), ICloudflareWorkersAiGenerationClient;

    private sealed class ListLogger : ILogger<FailoverGenerationClient>
    {
        public List<string> Messages { get; } = [];

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            Messages.Add(formatter(state, exception));
        }
    }
}
