using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Ringkas.Api.Generation;

public static class OpenCodeZenModels
{
    public const string MiMoV25Free = "mimo-v2.5-free";
    public const string MuseSpark12 = "muse-spark-1.2";

    public static bool IsSupported(string? model) => model is MiMoV25Free or MuseSpark12;
}

public sealed class OpenCodeZenGenerationClient(HttpClient httpClient, IConfiguration configuration) : IOpenCodeZenGenerationClient
{
    private const string DefaultBaseUrl = "https://opencode.ai/zen/v1";
    private const string DefaultAllowedHost = "opencode.ai";

    public async Task<GenerationResult> GenerateWithModelAsync(
        GenerationRequest request,
        string model,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        var settings = ReadSettings();
        if (!OpenCodeZenModels.IsSupported(model))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "OpenCode Zen generation model is invalid.");
        }

        using var timeoutSource = new CancellationTokenSource(TimeSpan.FromSeconds(settings.TimeoutSeconds));
        using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);
        var useResponsesApi = model == OpenCodeZenModels.MuseSpark12;
        var endpoint = new Uri(settings.BaseUrl, useResponsesApi ? "responses" : "chat/completions");
        object body;
        if (useResponsesApi)
        {
            body = new
            {
                model,
                input = request.Messages.Select(item => new
                {
                    role = NvidiaNimGenerationClient.ToWireRole(item.Role),
                    content = item.Content
                }),
                stream = false
            };
        }
        else
        {
            body = new
            {
                model,
                messages = request.Messages.Select(item => new
                {
                    role = NvidiaNimGenerationClient.ToWireRole(item.Role),
                    content = item.Content
                }),
                stream = false
            };
        }

        using var message = new HttpRequestMessage(HttpMethod.Post, endpoint);
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", settings.ApiKey);
        message.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8);
        message.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");

        HttpResponseMessage response;
        try
        {
            response = await httpClient.SendAsync(message, linkedSource.Token);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "OpenCode Zen generation timed out.");
        }
        catch (HttpRequestException) when (cancellationToken.IsCancellationRequested)
        {
            cancellationToken.ThrowIfCancellationRequested();
            throw;
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "OpenCode Zen generation is unavailable.");
        }

        using (response)
        {
            ThrowForStatus(response);
            var responseContent = await ReadContentAsync(response, linkedSource.Token, cancellationToken);
            return useResponsesApi
                ? GenerationResponseParser.ParseResponsesApi(responseContent, GenerationProvider.OpenCodeZen, model)
                : GenerationResponseParser.Parse(responseContent, GenerationProvider.OpenCodeZen, model);
        }
    }

    private OpenCodeZenSettings ReadSettings()
    {
        var apiKey = configuration["OPENCODE_ZEN_API_KEY"];
        var baseUrl = configuration["OPENCODE_ZEN_BASE_URL"] ?? DefaultBaseUrl;
        var allowedHosts = configuration["OPENCODE_ZEN_ALLOWED_HOSTS"] ?? DefaultAllowedHost;
        var timeout = configuration["OPENCODE_ZEN_TIMEOUT_SECONDS"] ?? "60";
        if (!IsSafeCredential(apiKey) || !TryReadTimeout(timeout, out var timeoutSeconds) ||
            !TryReadAllowedAuthority(allowedHosts, out var approvedHost) ||
            !TryReadBaseUrl(baseUrl, approvedHost, out var parsed))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "OpenCode Zen generation configuration is invalid.");
        }

        var normalized = new UriBuilder(parsed) { Query = string.Empty, Fragment = string.Empty }.Uri.AbsoluteUri.TrimEnd('/') + "/";
        return new OpenCodeZenSettings(apiKey!, new Uri(normalized, UriKind.Absolute), timeoutSeconds);
    }

    private static bool TryReadBaseUrl(string? value, string approvedHost, out Uri parsed)
    {
        parsed = null!;
        try
        {
            if (!Uri.TryCreate(value, UriKind.Absolute, out var candidate) || candidate is null)
            {
                return false;
            }

            parsed = candidate;
            return parsed.Scheme == Uri.UriSchemeHttps &&
                string.IsNullOrEmpty(parsed.UserInfo) &&
                string.IsNullOrEmpty(parsed.Query) &&
                string.IsNullOrEmpty(parsed.Fragment) &&
                parsed.AbsolutePath.TrimEnd('/') == "/zen/v1" &&
                string.Equals(parsed.Authority, approvedHost, StringComparison.OrdinalIgnoreCase);
        }
        catch (UriFormatException)
        {
            return false;
        }
    }

    private static bool TryReadAllowedAuthority(string? value, out string authority)
    {
        authority = string.Empty;
        if (string.IsNullOrWhiteSpace(value) || value.Contains(',', StringComparison.Ordinal))
        {
            return false;
        }

        try
        {
            if (value.Any(char.IsWhiteSpace) || value.Contains('*', StringComparison.Ordinal) ||
                !Uri.TryCreate($"https://{value}", UriKind.Absolute, out var parsed) ||
                parsed is null || parsed.Scheme != Uri.UriSchemeHttps ||
                !string.IsNullOrEmpty(parsed.UserInfo) || !string.IsNullOrEmpty(parsed.Query) ||
                !string.IsNullOrEmpty(parsed.Fragment) || parsed.AbsolutePath != "/" ||
                !string.Equals(parsed.Authority, value, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            authority = parsed.Authority;
            return true;
        }
        catch (UriFormatException)
        {
            return false;
        }
    }

    private static bool IsSafeCredential(string? value) =>
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
            throw new GenerationException(GenerationFailureCategory.Timeout, "OpenCode Zen generation timed out.");
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "OpenCode Zen generation is unavailable.");
        }
    }

    private static void ThrowForStatus(HttpResponseMessage response)
    {
        var statusCode = (int)response.StatusCode;
        if (response.StatusCode == HttpStatusCode.RequestTimeout)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "OpenCode Zen generation timed out.", statusCode);
        }

        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new GenerationException(GenerationFailureCategory.AuthenticationOrAuthorization, "OpenCode Zen generation authorization failed.", statusCode);
        }

        if (response.StatusCode == HttpStatusCode.TooManyRequests)
        {
            throw new GenerationException(GenerationFailureCategory.RateLimited, "OpenCode Zen generation was rate limited.", statusCode);
        }

        if (!response.IsSuccessStatusCode)
        {
            throw new GenerationException(GenerationFailureCategory.ProviderRejection, "OpenCode Zen generation request was rejected.", statusCode);
        }
    }

    private sealed class OpenCodeZenSettings(string apiKey, Uri baseUrl, double timeoutSeconds)
    {
        public string ApiKey { get; } = apiKey;

        public Uri BaseUrl { get; } = baseUrl;

        public double TimeoutSeconds { get; } = timeoutSeconds;
    }
}
