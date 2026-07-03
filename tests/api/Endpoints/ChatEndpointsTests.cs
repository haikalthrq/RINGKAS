using System.Text.Json;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;
using Ringkas.Api.Endpoints;
using Ringkas.Api.Generation;
using Ringkas.Api.Retrieval;

namespace Ringkas.Api.Tests.Endpoints;

public sealed class ChatEndpointsTests
{
    [Fact]
    public void RequestAcceptsSession()
    {
        Assert.Empty(new ChatRequest("question", Guid.NewGuid()).Validate());
    }

    [Fact]
    public void HistoryRoutesRequireRegisteredUserWhileChatRemainsAnonymous()
    {
        var builder = WebApplication.CreateBuilder();
        builder.Services.AddScoped<ChatService>();
        builder.Services.AddScoped<RingkasDbContext>();
        var app = builder.Build();
        app.MapChatEndpoints();
        var routes = ((IEndpointRouteBuilder)app).DataSources
            .SelectMany(source => source.Endpoints)
            .OfType<RouteEndpoint>()
            .ToArray();

        var chat = Assert.Single(routes, route => route.RoutePattern.RawText == "/api/chat");
        Assert.NotNull(chat.Metadata.GetMetadata<IAllowAnonymous>());
        foreach (var history in routes.Where(route => route.RoutePattern.RawText?.StartsWith("/api/chat/sessions", StringComparison.Ordinal) == true))
        {
            Assert.Equal(AuthorizationPolicies.RegisteredUser, history.Metadata.GetMetadata<IAuthorizeData>()?.Policy);
        }
        Assert.Equal(2, routes.Count(route => route.RoutePattern.RawText?.StartsWith("/api/chat/sessions", StringComparison.Ordinal) == true));
    }

    [Fact]
    public void OwnershipQueriesFilterByCurrentUserAndSession()
    {
        var ownId = Guid.NewGuid();
        var foreignId = Guid.NewGuid();
        var sessions = new[]
        {
            new ChatSession { Id = ownId, UserId = "current" },
            new ChatSession { Id = foreignId, UserId = "other" }
        }.AsQueryable();

        Assert.Equal(ownId, Assert.Single(ChatEndpoints.OwnSessions(sessions, "current")).Id);
        Assert.Equal(ownId, Assert.Single(ChatEndpoints.OwnSession(sessions, ownId, "current")).Id);
        Assert.Empty(ChatEndpoints.OwnSession(sessions, foreignId, "current"));
    }

    [Fact]
    public void StageExchangePersistsOrderedPairWithSafeMetadata()
    {
        using var db = CreateDbContext();
        var session = new ChatSession { Id = Guid.NewGuid(), UserId = "user" };
        var citation = Citation();
        var response = new ChatResponse("Supported claim [1].", [new ChatCitation(
            citation.DocumentId, citation.ChunkId, citation.Title, citation.Year, citation.Region,
            citation.PageStart, citation.PageEnd, citation.SourceUrl, citation.Snippet)], "sufficient", "nvidia_nim");
        var now = DateTime.UtcNow;

        ChatEndpoints.StageExchange(db, session, "question", response, now);

        var messages = db.ChangeTracker.Entries<ChatMessage>()
            .Select(entry => entry.Entity)
            .OrderBy(message => message.CreatedAt)
            .ToArray();
        Assert.Collection(messages,
            message =>
            {
                Assert.Equal(ChatMessageRoles.User, message.Role);
                Assert.Null(message.CitationsJson);
                Assert.Null(message.Provider);
            },
            message =>
            {
                Assert.Equal(ChatMessageRoles.Assistant, message.Role);
                Assert.Equal(ChatMessageProviders.NvidiaNim, message.Provider);
                Assert.Single(ChatEndpoints.ReadCitations(message.CitationsJson));
            });
        Assert.Equal(messages[1].CreatedAt, session.UpdatedAt);
    }

    [Fact]
    public void HistoryModelDropsMalformedCitationsAndUnknownProvider()
    {
        using var malformed = JsonDocument.Parse("{}");

        Assert.Empty(ChatEndpoints.ReadCitations(malformed));
        Assert.Null(ChatEndpoints.ApprovedProvider("unknown"));
        Assert.Equal(500, ChatEndpoints.CreateTitle(new string('a', 501)).Length);
    }

    [Fact]
    public async Task InsufficientEvidenceRefusesWithoutGeneration()
    {
        var generation = new FakeGenerationClient("unused");
        var chat = new ChatService(new FakeRetrievalClient(Response("insufficient", true, [])), generation);

        var response = await chat.AnswerAsync("question");

        Assert.Null(response.Provider);
        Assert.Equal(0, generation.CallCount);
        Assert.Equal("insufficient", response.SourceSufficiency);
    }

    [Fact]
    public async Task PartialEvidenceReturnsCitedLimitedAnswer()
    {
        var citation = Citation();
        var chat = new ChatService(new FakeRetrievalClient(Response("partial", false, [citation])), new FakeGenerationClient("Supported claim [1]."));

        var response = await chat.AnswerAsync("question");

        Assert.Equal("nvidia_nim", response.Provider);
        Assert.StartsWith("Keterbatasan:", response.Answer);
        Assert.Single(response.Citations);
    }

    [Fact]
    public async Task UncitedProviderOutputIsReplacedWithRefusal()
    {
        var chat = new ChatService(new FakeRetrievalClient(Response("partial", false, [Citation()])), new FakeGenerationClient("Unsupported claim."));

        var response = await chat.AnswerAsync("question");

        Assert.Null(response.Provider);
        Assert.DoesNotContain("Unsupported claim", response.Answer);
    }

    [Fact]
    public async Task UncitedFirstParagraphIsRejectedEvenWhenSecondIsCited()
    {
        var chat = new ChatService(new FakeRetrievalClient(Response("partial", false, [Citation()])), new FakeGenerationClient("Unsupported first paragraph.\n\nSupported second paragraph [1]."));

        var response = await chat.AnswerAsync("question");

        Assert.Null(response.Provider);
        Assert.DoesNotContain("Unsupported first paragraph", response.Answer);
    }

    [Theory]
    [InlineData("Claim [1] and malformed [source].")]
    [InlineData("Claim [1] and out of range [2].")]
    public async Task MixedMalformedOrOutOfRangeLabelsAreRejected(string generated)
    {
        var chat = new ChatService(new FakeRetrievalClient(Response("partial", false, [Citation()])), new FakeGenerationClient(generated));

        var response = await chat.AnswerAsync("question");

        Assert.Null(response.Provider);
        Assert.DoesNotContain(generated, response.Answer);
    }

    private static InternalRetrievalResponse Response(string sufficiency, bool refusal, IReadOnlyList<InternalRetrievalCitation> citations) =>
        new(sufficiency, sufficiency != "sufficient", refusal, sufficiency == "sufficient" ? null : "Limited evidence.", citations);

    private static InternalRetrievalCitation Citation() =>
        new(Guid.NewGuid(), Guid.NewGuid(), "Statistik DKI", 2026, "DKI Jakarta", 1, 1, "https://bps.go.id/source", "Relevant evidence.");

    private static RingkasDbContext CreateDbContext() => new(
        new DbContextOptionsBuilder<RingkasDbContext>()
            .UseNpgsql("Host=localhost;Database=ringkas_test;Username=ringkas;Password=ringkas")
            .Options);

    private sealed class FakeRetrievalClient(InternalRetrievalResponse response) : IInternalRetrievalClient
    {
        public Task<InternalRetrievalResponse> RetrieveAsync(string question, CancellationToken cancellationToken = default) => Task.FromResult(response);
    }

    private sealed class FakeGenerationClient(string text) : IGenerationClient
    {
        public int CallCount { get; private set; }

        public Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
        {
            CallCount++;
            return Task.FromResult(new GenerationResult(text, GenerationProvider.NvidiaNim, "test-model"));
        }
    }
}
