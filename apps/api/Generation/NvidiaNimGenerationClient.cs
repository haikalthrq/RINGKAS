using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Ringkas.Api.Generation;

public sealed class NvidiaNimGenerationClient(HttpClient httpClient, IConfiguration configuration) : INvidiaNimGenerationClient
{
    public async Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        var settings = ReadSettings();
        using var timeoutSource = new CancellationTokenSource(TimeSpan.FromSeconds(settings.TimeoutSeconds));
        using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);

        using var message = new HttpRequestMessage(HttpMethod.Post, new Uri(settings.BaseUrl, "chat/completions"));
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", settings.ApiKey);
        message.Content = new StringContent(JsonSerializer.Serialize(new
        {
            model = settings.Model,
            messages = request.Messages.Select(item => new { role = ToWireRole(item.Role), content = item.Content }),
            stream = false
        }), Encoding.UTF8, "application/json");

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
            throw new GenerationException(GenerationFailureCategory.Timeout, "NVIDIA NIM generation timed out.");
        }
        catch (HttpRequestException) when (cancellationToken.IsCancellationRequested)
        {
            cancellationToken.ThrowIfCancellationRequested();
            throw;
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "NVIDIA NIM generation is unavailable.");
        }

        using (response)
        {
            ThrowForStatus(response);
            var responseContent = await ReadContentAsync(response, linkedSource.Token, cancellationToken);
            return GenerationResponseParser.Parse(responseContent, GenerationProvider.NvidiaNim, settings.Model);
        }
    }

    private NvidiaSettings ReadSettings()
    {
        var apiKey = configuration["NVIDIA_NIM_API_KEY"];
        var model = configuration["NVIDIA_NIM_GENERATION_MODEL"];
        var baseUrl = configuration["NVIDIA_NIM_GENERATION_BASE_URL"];
        var allowedHosts = configuration["NVIDIA_NIM_GENERATION_ALLOWED_HOSTS"];
        var timeout = configuration["NVIDIA_NIM_GENERATION_TIMEOUT_SECONDS"];
        if (!IsSafeCredential(apiKey) || string.IsNullOrWhiteSpace(model) ||
            !TryReadTimeout(timeout, out var timeoutSeconds) || !TryReadAllowedAuthorities(allowedHosts, out var approvedAuthorities))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "NVIDIA NIM generation configuration is invalid.");
        }

        if (!TryReadBaseUrl(baseUrl, approvedAuthorities, out var parsed))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "NVIDIA NIM generation configuration is invalid.");
        }

        var normalized = new UriBuilder(parsed) { Query = string.Empty, Fragment = string.Empty }.Uri.AbsoluteUri.TrimEnd('/') + "/";
        return new NvidiaSettings(apiKey!, model!, new Uri(normalized, UriKind.Absolute), timeoutSeconds);
    }

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
            throw new GenerationException(GenerationFailureCategory.Timeout, "NVIDIA NIM generation timed out.");
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "NVIDIA NIM generation is unavailable.");
        }
    }

    private static bool TryReadTimeout(string? value, out double timeoutSeconds) =>
        double.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out timeoutSeconds) &&
        double.IsFinite(timeoutSeconds) && timeoutSeconds is >= 1 and <= 300;

    private static bool IsOpenAiV1Base(Uri parsed, string? rawValue) =>
        !string.IsNullOrWhiteSpace(rawValue) &&
        !rawValue.Contains("..", StringComparison.Ordinal) &&
        !rawValue.Contains("%2e", StringComparison.OrdinalIgnoreCase) &&
        parsed.AbsolutePath.TrimEnd('/') == "/v1";

    private static bool TryReadBaseUrl(string? value, IEnumerable<string> approvedAuthorities, out Uri parsed)
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
                IsOpenAiV1Base(parsed, value) &&
                approvedAuthorities.Contains(parsed.Authority, StringComparer.OrdinalIgnoreCase);
        }
        catch (UriFormatException)
        {
            return false;
        }
    }

    private static bool IsSafeCredential(string? value) =>
        !string.IsNullOrWhiteSpace(value) && !value.Any(char.IsWhiteSpace);

    private static bool TryReadAllowedAuthorities(string? value, out string[] authorities)
    {
        authorities = [];
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        var entries = value.Split(',', StringSplitOptions.None).Select(entry => entry.Trim()).ToArray();
        if (entries.Length == 0 || entries.Any(string.IsNullOrWhiteSpace))
        {
            return false;
        }

        var approved = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in entries)
        {
            try
            {
                if (entry.Contains("*", StringComparison.Ordinal) || entry.Any(char.IsWhiteSpace) ||
                    !Uri.TryCreate($"https://{entry}", UriKind.Absolute, out var parsed) ||
                    parsed.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(parsed.UserInfo) ||
                    !string.IsNullOrEmpty(parsed.Query) || !string.IsNullOrEmpty(parsed.Fragment) ||
                    parsed.AbsolutePath != "/" || !string.Equals(parsed.Authority, entry, StringComparison.OrdinalIgnoreCase) ||
                    !approved.Add(parsed.Authority))
                {
                    return false;
                }
            }
            catch (UriFormatException)
            {
                return false;
            }
        }

        authorities = approved.ToArray();
        return true;
    }

    private static void ThrowForStatus(HttpResponseMessage response)
    {
        var statusCode = (int)response.StatusCode;
        if (response.StatusCode == HttpStatusCode.RequestTimeout)
        {
            throw new GenerationException(GenerationFailureCategory.Timeout, "NVIDIA NIM generation timed out.", statusCode);
        }

        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new GenerationException(GenerationFailureCategory.AuthenticationOrAuthorization, "NVIDIA NIM generation authorization failed.", statusCode);
        }

        if (response.StatusCode == HttpStatusCode.TooManyRequests)
        {
            throw new GenerationException(GenerationFailureCategory.RateLimited, "NVIDIA NIM generation was rate limited.", statusCode);
        }

        if (!response.IsSuccessStatusCode)
        {
            throw new GenerationException(GenerationFailureCategory.ProviderRejection, "NVIDIA NIM generation request was rejected.", statusCode);
        }
    }

    internal static string ToWireRole(GenerationRole role) => role switch
    {
        GenerationRole.System => "system",
        GenerationRole.User => "user",
        GenerationRole.Assistant => "assistant",
        _ => throw new GenerationException(GenerationFailureCategory.InvalidRequest, "Generation message role is invalid.")
    };

    private sealed class NvidiaSettings(string apiKey, string model, Uri baseUrl, double timeoutSeconds)
    {
        public string ApiKey { get; } = apiKey;

        public string Model { get; } = model;

        public Uri BaseUrl { get; } = baseUrl;

        public double TimeoutSeconds { get; } = timeoutSeconds;

        public override string ToString() => "NvidiaSettings { [REDACTED] }";
    }
}
