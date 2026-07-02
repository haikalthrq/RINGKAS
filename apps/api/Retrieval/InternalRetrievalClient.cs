using System.Globalization;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Ringkas.Api.Retrieval;

public interface IInternalRetrievalClient
{
    Task<InternalRetrievalResponse> RetrieveAsync(string question, CancellationToken cancellationToken = default);
}

public sealed record InternalRetrievalCitation(
    [property: JsonPropertyName("document_id")] Guid DocumentId,
    [property: JsonPropertyName("chunk_id")] Guid ChunkId,
    string Title,
    int Year,
    string Region,
    [property: JsonPropertyName("page_start")] int? PageStart,
    [property: JsonPropertyName("page_end")] int? PageEnd,
    [property: JsonPropertyName("source_url")] string SourceUrl,
    string Snippet);

public sealed record InternalRetrievalResponse(
    [property: JsonPropertyName("source_sufficiency")] string SourceSufficiency,
    [property: JsonPropertyName("requires_limitation")] bool RequiresLimitation,
    [property: JsonPropertyName("requires_refusal")] bool RequiresRefusal,
    [property: JsonPropertyName("limitation_reason")] string? LimitationReason,
    IReadOnlyList<InternalRetrievalCitation> Citations);

public sealed class InternalRetrievalException(string message) : Exception(message);

public sealed class InternalRetrievalClient(HttpClient httpClient, IConfiguration configuration) : IInternalRetrievalClient
{
    private const int MaxResponseBytes = 256 * 1024;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow
    };

    public async Task<InternalRetrievalResponse> RetrieveAsync(string question, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(question))
        {
            throw new InternalRetrievalException("Retrieval question is invalid.");
        }
        var settings = ReadSettings();
        using var timeout = new CancellationTokenSource(settings.Timeout);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(settings.BaseUrl, "retrieve"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", settings.Token);
        request.Content = new StringContent(JsonSerializer.Serialize(new { question }), Encoding.UTF8, "application/json");
        try
        {
            using var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, linked.Token);
            if (!response.IsSuccessStatusCode || response.Content.Headers.ContentType?.MediaType != "application/json" || response.Content.Headers.ContentLength > MaxResponseBytes)
            {
                throw new InternalRetrievalException("Internal retrieval is unavailable.");
            }
            await using var stream = await response.Content.ReadAsStreamAsync(linked.Token);
            using var content = new MemoryStream();
            var buffer = new byte[8192];
            int read;
            while ((read = await stream.ReadAsync(buffer, linked.Token)) > 0)
            {
                if (content.Length + read > MaxResponseBytes)
                {
                    throw new InternalRetrievalException("Internal retrieval returned an invalid response.");
                }
                content.Write(buffer, 0, read);
            }
            content.Position = 0;
            var result = await JsonSerializer.DeserializeAsync<InternalRetrievalResponse>(content, JsonOptions, linked.Token);
            return Validate(result);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (InternalRetrievalException)
        {
            throw;
        }
        catch (Exception)
        {
            throw new InternalRetrievalException("Internal retrieval is unavailable.");
        }
    }

    private Settings ReadSettings()
    {
        var rawBaseUrl = configuration["RAG_QUERY_BASE_URL"];
        var token = configuration["RAG_INTERNAL_TOKEN"];
        var authorities = configuration["RAG_QUERY_ALLOWED_AUTHORITIES"]?.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        if (string.IsNullOrWhiteSpace(rawBaseUrl) || token is null || token.Length < 32 || token.Any(char.IsWhiteSpace) ||
            authorities is null || authorities.Length == 0 || authorities.Distinct(StringComparer.OrdinalIgnoreCase).Count() != authorities.Length ||
            !double.TryParse(configuration["RAG_QUERY_TIMEOUT_SECONDS"], NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds) || seconds is < 1 or > 120 ||
            !Uri.TryCreate(rawBaseUrl, UriKind.Absolute, out var baseUrl) || baseUrl is null ||
            baseUrl.Scheme is not ("http" or "https") || !string.IsNullOrEmpty(baseUrl.UserInfo) || !string.IsNullOrEmpty(baseUrl.Query) ||
            !string.IsNullOrEmpty(baseUrl.Fragment) || baseUrl.AbsolutePath != "/" ||
            !authorities.Contains(baseUrl.Authority, StringComparer.OrdinalIgnoreCase) ||
            authorities.Any(authority => authority.Any(char.IsWhiteSpace) || authority.Contains('*') || !Uri.TryCreate($"http://{authority}", UriKind.Absolute, out var parsed) || parsed.Authority != authority || parsed.AbsolutePath != "/"))
        {
            throw new InternalRetrievalException("Internal retrieval configuration is invalid.");
        }
        return new Settings(baseUrl, token, TimeSpan.FromSeconds(seconds));
    }

    private static InternalRetrievalResponse Validate(InternalRetrievalResponse? response)
    {
        if (response is null || response.SourceSufficiency is not ("sufficient" or "partial" or "insufficient") || response.Citations is null || response.Citations.Count > 10 ||
            response.RequiresRefusal != (response.SourceSufficiency == "insufficient") ||
            response.RequiresLimitation != (response.SourceSufficiency != "sufficient") ||
            (response.RequiresLimitation ? string.IsNullOrWhiteSpace(response.LimitationReason) : response.LimitationReason is not null) ||
            response.SourceSufficiency != "insufficient" && response.Citations.Count == 0)
        {
            throw new InternalRetrievalException("Internal retrieval returned an invalid response.");
        }
        var ids = new HashSet<Guid>();
        foreach (var citation in response.Citations)
        {
            if (citation.DocumentId == Guid.Empty || citation.ChunkId == Guid.Empty || !ids.Add(citation.ChunkId) ||
                string.IsNullOrWhiteSpace(citation.Title) || citation.Year <= 0 || string.IsNullOrWhiteSpace(citation.Region) ||
                string.IsNullOrWhiteSpace(citation.Snippet) || citation.Snippet.Length > 20_000 ||
                (citation.PageStart is null) != (citation.PageEnd is null) || citation.PageStart is <= 0 || citation.PageEnd < citation.PageStart ||
                !Uri.TryCreate(citation.SourceUrl, UriKind.Absolute, out var source) || source.Scheme is not ("http" or "https") || !string.IsNullOrEmpty(source.UserInfo))
            {
                throw new InternalRetrievalException("Internal retrieval returned an invalid response.");
            }
        }
        return response;
    }

    private sealed record Settings(Uri BaseUrl, string Token, TimeSpan Timeout)
    {
        public override string ToString() => "Settings { [REDACTED] }";
    }
}

public static class InternalRetrievalServiceCollectionExtensions
{
    public static IServiceCollection AddInternalRetrieval(this IServiceCollection services)
    {
        services.AddHttpClient<IInternalRetrievalClient, InternalRetrievalClient>(client => client.Timeout = Timeout.InfiniteTimeSpan);
        return services;
    }
}
