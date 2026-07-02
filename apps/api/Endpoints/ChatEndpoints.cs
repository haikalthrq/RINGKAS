using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.RateLimiting;
using Ringkas.Api.Auth;
using Ringkas.Api.Generation;
using Ringkas.Api.Retrieval;

namespace Ringkas.Api.Endpoints;

public static partial class ChatEndpoints
{
    public static IEndpointRouteBuilder MapChatEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/chat", HandleAsync)
            .AllowAnonymous()
            .RequireRateLimiting(RateLimitPolicies.Chat);
        return endpoints;
    }

    private static async Task<IResult> HandleAsync(ChatRequest request, ChatService chat, ILogger<ChatService> logger, CancellationToken cancellationToken)
    {
        var errors = request.Validate();
        if (errors.Count > 0)
        {
            return Results.ValidationProblem(errors);
        }
        try
        {
            return Results.Ok(await chat.AnswerAsync(request.Message.Trim(), cancellationToken));
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (InternalRetrievalException)
        {
            logger.LogWarning("Chat retrieval failed.");
            return Results.Problem("Chat retrieval is temporarily unavailable.", statusCode: StatusCodes.Status503ServiceUnavailable);
        }
        catch (GenerationException)
        {
            logger.LogWarning("Chat generation failed.");
            return Results.Problem("Chat generation is temporarily unavailable.", statusCode: StatusCodes.Status503ServiceUnavailable);
        }
    }

    [GeneratedRegex(@"\[([0-9]+)\]", RegexOptions.CultureInvariant)]
    internal static partial Regex CitationLabelPattern();
}

public sealed record ChatRequest(string Message, [property: JsonPropertyName("session_id")] Guid? SessionId)
{
    public Dictionary<string, string[]> Validate()
    {
        var errors = new Dictionary<string, string[]>();
        if (string.IsNullOrWhiteSpace(Message) || Message.Length > 2_000)
        {
            errors["message"] = ["Message must be nonblank and no longer than 2000 characters."];
        }
        if (SessionId is not null)
        {
            errors["session_id"] = ["Chat sessions are not supported yet."];
        }
        return errors;
    }
}

public sealed record ChatCitation(
    [property: JsonPropertyName("document_id")] Guid DocumentId,
    [property: JsonPropertyName("chunk_id")] Guid ChunkId,
    string Title,
    int Year,
    string Region,
    [property: JsonPropertyName("page_start")] int? PageStart,
    [property: JsonPropertyName("page_end")] int? PageEnd,
    [property: JsonPropertyName("source_url")] string SourceUrl,
    string Snippet);

public sealed record ChatResponse(
    string Answer,
    IReadOnlyList<ChatCitation> Citations,
    [property: JsonPropertyName("source_sufficiency")] string SourceSufficiency,
    string? Provider);

public sealed class ChatService(IInternalRetrievalClient retrieval, IGenerationClient generation)
{
    private const string Refusal = "Sumber yang tersedia belum cukup relevan untuk memberikan jawaban substantif. Silakan perjelas pertanyaan atau coba kembali setelah sumber yang sesuai tersedia.";
    private const string Limited = "Keterbatasan: bukti sumber yang ditemukan masih terbatas. ";

    public async Task<ChatResponse> AnswerAsync(string question, CancellationToken cancellationToken = default)
    {
        var result = await retrieval.RetrieveAsync(question, cancellationToken);
        var citations = result.Citations.Select(citation => new ChatCitation(
            citation.DocumentId, citation.ChunkId, citation.Title, citation.Year, citation.Region,
            citation.PageStart, citation.PageEnd, citation.SourceUrl, citation.Snippet)).ToArray();
        if (result.RequiresRefusal)
        {
            return new ChatResponse(Refusal, citations, result.SourceSufficiency, null);
        }

        var generated = await generation.GenerateAsync(GroundedPromptTemplate.Create(question, result.Citations.Select(citation => citation.Snippet)), cancellationToken);
        if (!HasValidCitationsOnEveryLine(generated.Text, citations.Length))
        {
            return new ChatResponse(Refusal, citations, result.SourceSufficiency, null);
        }
        var answer = result.RequiresLimitation ? Limited + generated.Text.Trim() : generated.Text.Trim();
        var provider = generated.Provider == GenerationProvider.NvidiaNim ? "nvidia_nim" : "cloudflare_workers_ai";
        return new ChatResponse(answer, citations, result.SourceSufficiency, provider);
    }

    private static bool HasValidCitationsOnEveryLine(string text, int citationCount)
    {
        foreach (var line in text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n').Split('\n'))
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }
            var labels = ChatEndpoints.CitationLabelPattern().Matches(line);
            if (labels.Count == 0 ||
                labels.Any(match => !int.TryParse(match.Groups[1].Value, out var label) || label < 1 || label > citationCount) ||
                ChatEndpoints.CitationLabelPattern().Replace(line, string.Empty).IndexOfAny(['[', ']']) >= 0)
            {
                return false;
            }
        }
        return true;
    }
}
