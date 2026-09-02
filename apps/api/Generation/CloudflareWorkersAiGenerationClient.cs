using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Ringkas.Api.Generation;

public sealed class CloudflareWorkersAiGenerationClient(HttpClient httpClient, IConfiguration configuration) : ICloudflareWorkersAiGenerationClient, IModelOverrideGenerationClient
{
    public Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default) =>
        GenerateWithModelAsync(request, ReadSettings().Model, cancellationToken);

    public async Task<GenerationResult> GenerateWithModelAsync(
        GenerationRequest request,
        string model,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        var settings = ReadSettings();
        if (!IsSafeModel(model))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }

        GenerationException? lastFailure = null;
        foreach (var target in settings.Targets)
        {
            try
            {
                using var timeoutSource = new CancellationTokenSource(TimeSpan.FromSeconds(settings.TimeoutSeconds));
                using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);
                using var message = CreateRequest(target, request, model);
                using var response = await SendAsync(message, linkedSource.Token, cancellationToken);
                ThrowForStatus(response);
                var responseContent = await ReadContentAsync(response, linkedSource.Token, cancellationToken);
                return GenerationResponseParser.Parse(responseContent, GenerationProvider.CloudflareWorkersAi, model);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (GenerationException failure) when (IsAccountFailoverEligible(failure))
            {
                lastFailure = failure;
            }
        }

        if (lastFailure is not null)
        {
            throw lastFailure;
        }

        throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
    }

    private CloudflareSettings ReadSettings()
    {
        var accountId = configuration["CLOUDFLARE_ACCOUNT_ID"];
        var apiToken = configuration["CLOUDFLARE_API_TOKEN"] ?? configuration["CLOUDFLARE_WORKERS_AI_TOKEN"];
        var model = configuration["CLOUDFLARE_WORKERS_AI_GENERATION_MODEL"];
        var timeout = configuration["CLOUDFLARE_WORKERS_AI_GENERATION_TIMEOUT_SECONDS"];
        if (!IsSafeAccountId(accountId) || !IsSafeCredential(apiToken) || string.IsNullOrWhiteSpace(model) || !TryReadTimeout(timeout, out var timeoutSeconds))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }

        var targets = new List<CloudflareTarget>();
        if (!TryAddTarget(targets, accountId!, apiToken!))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }

        if (!TryAddOptionalTarget(
                targets,
                configuration["CLOUDFLARE_WORKERS_AI_GENERATION_SECONDARY_ACCOUNT_ID"],
                configuration["CLOUDFLARE_WORKERS_AI_GENERATION_SECONDARY_API_TOKEN"]) ||
            !TryAddOptionalTarget(
                targets,
                configuration["CLOUDFLARE_WORKERS_AI_GENERATION_TERTIARY_ACCOUNT_ID"],
                configuration["CLOUDFLARE_WORKERS_AI_GENERATION_TERTIARY_API_TOKEN"]))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }

        return new CloudflareSettings(targets, model!, timeoutSeconds);
    }

    private static HttpRequestMessage CreateRequest(CloudflareTarget target, GenerationRequest request, string model)
    {
        var message = new HttpRequestMessage(HttpMethod.Post, target.Endpoint);
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", target.ApiToken);
        message.Content = new StringContent(JsonSerializer.Serialize(new
        {
            model,
            messages = request.Messages.Select(item => new { role = NvidiaNimGenerationClient.ToWireRole(item.Role), content = item.Content }),
            stream = false
        }), Encoding.UTF8, "application/json");
        return message;
    }

    private async Task<HttpResponseMessage> SendAsync(HttpRequestMessage message, CancellationToken linkedToken, CancellationToken callerToken)
    {
        try
        {
            return await httpClient.SendAsync(message, linkedToken);
        }
        catch (OperationCanceledException) when (callerToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "Cloudflare Workers AI generation timed out.");
        }
        catch (HttpRequestException) when (callerToken.IsCancellationRequested)
        {
            callerToken.ThrowIfCancellationRequested();
            throw;
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "Cloudflare Workers AI generation is unavailable.");
        }
    }

    private static bool TryAddOptionalTarget(ICollection<CloudflareTarget> targets, string? accountId, string? apiToken)
    {
        var hasAccount = !string.IsNullOrWhiteSpace(accountId);
        var hasToken = !string.IsNullOrWhiteSpace(apiToken);
        return !hasAccount && !hasToken || hasAccount && hasToken && TryAddTarget(targets, accountId!, apiToken!);
    }

    private static bool TryAddTarget(ICollection<CloudflareTarget> targets, string accountId, string apiToken)
    {
        if (!IsSafeAccountId(accountId) || !IsSafeCredential(apiToken) ||
            targets.Any(target => target.AccountId.Equals(accountId, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        try
        {
            targets.Add(new CloudflareTarget(
                accountId,
                apiToken,
                new Uri($"https://api.cloudflare.com/client/v4/accounts/{accountId}/ai/v1/chat/completions", UriKind.Absolute)));
            return true;
        }
        catch (UriFormatException)
        {
            return false;
        }
    }

    private static bool IsSafeAccountId(string? value) =>
        !string.IsNullOrWhiteSpace(value) && value.Length <= 128 && value.All(character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_');

    private static bool IsSafeCredential(string? value) =>
        !string.IsNullOrWhiteSpace(value) && !value.Any(char.IsWhiteSpace);

    private static bool IsSafeModel(string? value) =>
        !string.IsNullOrWhiteSpace(value) && !value.Any(char.IsWhiteSpace);

    private static bool TryReadTimeout(string? value, out double timeoutSeconds) =>
        double.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out timeoutSeconds) &&
        double.IsFinite(timeoutSeconds) && timeoutSeconds is >= 1 and <= 300;

    private static async Task<string> ReadContentAsync(HttpResponseMessage response, CancellationToken linkedToken, CancellationToken callerToken)
    {
        try
        {
            return await response.Content.ReadAsStringAsync(linkedToken);
        }
        catch (OperationCanceledException) when (callerToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "Cloudflare Workers AI generation timed out.");
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "Cloudflare Workers AI generation is unavailable.");
        }
    }

    private static void ThrowForStatus(HttpResponseMessage response)
    {
        var statusCode = (int)response.StatusCode;
        if (response.StatusCode == HttpStatusCode.RequestTimeout)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "Cloudflare Workers AI generation timed out.", statusCode);
        }

        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new GenerationException(GenerationFailureCategory.AuthenticationOrAuthorization, "Cloudflare Workers AI generation authorization failed.", statusCode);
        }

        if (response.StatusCode == HttpStatusCode.TooManyRequests)
        {
            throw new GenerationException(GenerationFailureCategory.RateLimited, "Cloudflare Workers AI generation was rate limited.", statusCode);
        }

        if (!response.IsSuccessStatusCode)
        {
            throw new GenerationException(GenerationFailureCategory.ProviderRejection, "Cloudflare Workers AI generation request was rejected.", statusCode);
        }
    }

    private static bool IsAccountFailoverEligible(GenerationException failure) =>
        failure.Category is GenerationFailureCategory.AuthenticationOrAuthorization or
            GenerationFailureCategory.RateLimited or
            GenerationFailureCategory.Timeout or
            GenerationFailureCategory.TransportUnavailable or
            GenerationFailureCategory.MalformedResponse ||
        (failure.Category == GenerationFailureCategory.ProviderRejection && failure.StatusCode is >= 500 and <= 599);

    private sealed class CloudflareSettings(IReadOnlyList<CloudflareTarget> targets, string model, double timeoutSeconds)
    {
        public IReadOnlyList<CloudflareTarget> Targets { get; } = targets;

        public string Model { get; } = model;

        public double TimeoutSeconds { get; } = timeoutSeconds;

        public override string ToString() => "CloudflareSettings { [REDACTED] }";
    }

    private sealed record CloudflareTarget(string AccountId, string ApiToken, Uri Endpoint);
}
