using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Ringkas.Api.Generation;

public sealed class CloudflareWorkersAiGenerationClient(HttpClient httpClient, IConfiguration configuration) : ICloudflareWorkersAiGenerationClient
{
    public async Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        var settings = ReadSettings();
        using var timeoutSource = new CancellationTokenSource(TimeSpan.FromSeconds(settings.TimeoutSeconds));
        using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);

        using var message = new HttpRequestMessage(HttpMethod.Post, settings.Endpoint);
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", settings.ApiToken);
        message.Content = new StringContent(JsonSerializer.Serialize(new
        {
            model = settings.Model,
            messages = request.Messages.Select(item => new { role = NvidiaNimGenerationClient.ToWireRole(item.Role), content = item.Content }),
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
            throw new GenerationException(GenerationFailureCategory.Timeout, "Cloudflare Workers AI generation timed out.");
        }
        catch (HttpRequestException) when (cancellationToken.IsCancellationRequested)
        {
            cancellationToken.ThrowIfCancellationRequested();
            throw;
        }
        catch (HttpRequestException)
        {
            throw new GenerationException(GenerationFailureCategory.TransportUnavailable, "Cloudflare Workers AI generation is unavailable.");
        }

        using (response)
        {
            ThrowForStatus(response);
            var responseContent = await ReadContentAsync(response, linkedSource.Token, cancellationToken);
            return GenerationResponseParser.Parse(responseContent, GenerationProvider.CloudflareWorkersAi, settings.Model);
        }
    }

    private CloudflareSettings ReadSettings()
    {
        var accountId = configuration["CLOUDFLARE_ACCOUNT_ID"];
        var apiToken = configuration["CLOUDFLARE_API_TOKEN"];
        var model = configuration["CLOUDFLARE_WORKERS_AI_MODEL"];
        var timeout = configuration["CLOUDFLARE_WORKERS_AI_TIMEOUT_SECONDS"];
        if (!IsSafeAccountId(accountId) || !IsSafeCredential(apiToken) || string.IsNullOrWhiteSpace(model) || !TryReadTimeout(timeout, out var timeoutSeconds))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }

        try
        {
            var endpoint = new Uri($"https://api.cloudflare.com/client/v4/accounts/{accountId}/ai/v1/chat/completions", UriKind.Absolute);
            return new CloudflareSettings(apiToken!, model!, endpoint, timeoutSeconds);
        }
        catch (UriFormatException)
        {
            throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Cloudflare Workers AI generation configuration is invalid.");
        }
    }

    private static bool IsSafeAccountId(string? value) =>
        !string.IsNullOrWhiteSpace(value) && value.Length <= 128 && value.All(character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_');

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

    private sealed class CloudflareSettings(string apiToken, string model, Uri endpoint, double timeoutSeconds)
    {
        public string ApiToken { get; } = apiToken;

        public string Model { get; } = model;

        public Uri Endpoint { get; } = endpoint;

        public double TimeoutSeconds { get; } = timeoutSeconds;

        public override string ToString() => "CloudflareSettings { [REDACTED] }";
    }
}
