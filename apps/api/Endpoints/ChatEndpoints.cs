using System.Security.Claims;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;
using Ringkas.Api.Generation;
using Ringkas.Api.Retrieval;

namespace Ringkas.Api.Endpoints;

public static partial class ChatEndpoints
{
    private const int HistoryLimit = 50;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static IEndpointRouteBuilder MapChatEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/chat", HandleAsync)
            .AllowAnonymous()
            .RequireRateLimiting(RateLimitPolicies.Chat);

        var history = endpoints.MapGroup("/api/chat/sessions")
            .RequireAuthorization(AuthorizationPolicies.RegisteredUser);
        history.MapGet("", ListSessionsAsync);
        history.MapGet("/{id:guid}", GetSessionAsync);

        return endpoints;
    }

    private static async Task<IResult> HandleAsync(
        ChatRequest request,
        ClaimsPrincipal user,
        ChatService chat,
        RingkasDbContext dbContext,
        ILogger<ChatService> logger,
        CancellationToken cancellationToken)
    {
        var errors = request.Validate();
        var userId = user.Identity?.IsAuthenticated == true
            ? user.FindFirstValue(ClaimTypes.NameIdentifier)
            : null;
        if (user.Identity?.IsAuthenticated == true && string.IsNullOrWhiteSpace(userId))
        {
            return Results.Unauthorized();
        }
        if (request.SessionId is not null && userId is null)
        {
            errors["session_id"] = ["Anonymous chat cannot use a session."];
        }
        if (errors.Count > 0)
        {
            return Results.ValidationProblem(errors);
        }

        ChatSession? session = null;
        if (request.SessionId is not null)
        {
            session = await OwnSession(dbContext.ChatSessions, request.SessionId.Value, userId!)
                .SingleOrDefaultAsync(cancellationToken);
            if (session is null)
            {
                return Results.NotFound();
            }
        }

        try
        {
            var question = request.Message.Trim();
            var response = await chat.AnswerAsync(question, cancellationToken);
            if (userId is null)
            {
                return Results.Ok(response);
            }

            var now = DateTime.UtcNow;
            session ??= new ChatSession
            {
                Id = Guid.NewGuid(),
                UserId = userId,
                Title = CreateTitle(question),
                CreatedAt = now,
                UpdatedAt = now
            };
            if (dbContext.Entry(session).State == EntityState.Detached)
            {
                dbContext.ChatSessions.Add(session);
            }

            StageExchange(dbContext, session, question, response, now);
            await dbContext.SaveChangesAsync(cancellationToken);
            return Results.Ok(response with { SessionId = session.Id });
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

    private static async Task<IResult> ListSessionsAsync(
        ClaimsPrincipal user,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var userId = user.FindFirstValue(ClaimTypes.NameIdentifier);
        if (string.IsNullOrWhiteSpace(userId))
        {
            return Results.Unauthorized();
        }

        var sessions = await OwnSessions(dbContext.ChatSessions, userId)
            .AsNoTracking()
            .OrderByDescending(session => session.UpdatedAt)
            .ThenByDescending(session => session.Id)
            .Take(HistoryLimit)
            .Select(session => new ChatSessionSummary(session.Id, session.Title, session.CreatedAt, session.UpdatedAt))
            .ToListAsync(cancellationToken);
        return Results.Ok(sessions);
    }

    private static async Task<IResult> GetSessionAsync(
        Guid id,
        ClaimsPrincipal user,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var userId = user.FindFirstValue(ClaimTypes.NameIdentifier);
        if (string.IsNullOrWhiteSpace(userId))
        {
            return Results.Unauthorized();
        }

        var session = await OwnSession(dbContext.ChatSessions, id, userId)
            .AsNoTracking()
            .Select(item => new ChatSessionSummary(item.Id, item.Title, item.CreatedAt, item.UpdatedAt))
            .SingleOrDefaultAsync(cancellationToken);
        if (session is null)
        {
            return Results.NotFound();
        }

        var storedMessages = await dbContext.ChatMessages
            .AsNoTracking()
            .Where(message => message.SessionId == session.SessionId)
            .OrderBy(message => message.CreatedAt)
            .ThenBy(message => message.Id)
            .ToListAsync(cancellationToken);
        var messages = storedMessages.Select(message => new ChatHistoryMessage(
            message.Id,
            message.Role,
            message.Content,
            ReadCitations(message.CitationsJson),
            ApprovedProvider(message.Provider),
            message.CreatedAt)).ToList();

        return Results.Ok(new ChatSessionDetail(
            session.SessionId,
            session.Title,
            session.CreatedAt,
            session.UpdatedAt,
            messages));
    }

    internal static IQueryable<ChatSession> OwnSessions(IQueryable<ChatSession> sessions, string userId) =>
        sessions.Where(session => session.UserId == userId);

    internal static IQueryable<ChatSession> OwnSession(IQueryable<ChatSession> sessions, Guid sessionId, string userId) =>
        sessions.Where(session => session.Id == sessionId && session.UserId == userId);

    internal static string CreateTitle(string question) => question[..Math.Min(question.Length, 500)];

    internal static void StageExchange(
        RingkasDbContext dbContext,
        ChatSession session,
        string question,
        ChatResponse response,
        DateTime createdAt)
    {
        var assistantCreatedAt = createdAt.AddMilliseconds(1);
        session.UpdatedAt = assistantCreatedAt;
        dbContext.ChatMessages.AddRange(
            new ChatMessage
            {
                Id = Guid.NewGuid(),
                SessionId = session.Id,
                Role = ChatMessageRoles.User,
                Content = question,
                CreatedAt = createdAt
            },
            new ChatMessage
            {
                Id = Guid.NewGuid(),
                SessionId = session.Id,
                Role = ChatMessageRoles.Assistant,
                Content = response.Answer,
                CitationsJson = JsonSerializer.SerializeToDocument(response.Citations, JsonOptions),
                Provider = ApprovedProvider(response.Provider),
                CreatedAt = assistantCreatedAt
            });
    }

    internal static IReadOnlyList<ChatCitation> ReadCitations(JsonDocument? citations)
    {
        if (citations is null || citations.RootElement.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        try
        {
            return citations.Deserialize<ChatCitation[]>(JsonOptions) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    internal static string? ApprovedProvider(string? provider) => provider is
        ChatMessageProviders.NvidiaNim or ChatMessageProviders.CloudflareWorkersAi ? provider : null;

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
    string? Provider,
    [property: JsonPropertyName("session_id")] Guid? SessionId = null);

public sealed record ChatSessionSummary(
    [property: JsonPropertyName("session_id")] Guid SessionId,
    string? Title,
    [property: JsonPropertyName("created_at")] DateTime CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTime UpdatedAt);

public sealed record ChatHistoryMessage(
    [property: JsonPropertyName("message_id")] Guid MessageId,
    string Role,
    string Content,
    IReadOnlyList<ChatCitation> Citations,
    string? Provider,
    [property: JsonPropertyName("created_at")] DateTime CreatedAt);

public sealed record ChatSessionDetail(
    [property: JsonPropertyName("session_id")] Guid SessionId,
    string? Title,
    [property: JsonPropertyName("created_at")] DateTime CreatedAt,
    [property: JsonPropertyName("updated_at")] DateTime UpdatedAt,
    IReadOnlyList<ChatHistoryMessage> Messages);

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
