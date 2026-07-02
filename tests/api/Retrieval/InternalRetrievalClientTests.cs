using System.Net;
using System.Text;
using Microsoft.Extensions.Configuration;
using Ringkas.Api.Retrieval;

namespace Ringkas.Api.Tests.Retrieval;

public sealed class InternalRetrievalClientTests
{
    private const string InternalToken = "12345678901234567890123456789012";

    [Fact]
    public async Task SendsAuthenticatedRequestAndValidatesResponse()
    {
        var handler = new DelegateHandler(request =>
        {
            Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
            Assert.Equal(InternalToken, request.Headers.Authorization?.Parameter);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(ValidResponse, Encoding.UTF8, "application/json")
            };
        });
        var client = new InternalRetrievalClient(new HttpClient(handler), Configuration());

        var response = await client.RetrieveAsync("kemiskinan");

        Assert.Equal("partial", response.SourceSufficiency);
        Assert.Single(response.Citations);
    }

    [Fact]
    public async Task RejectsUnapprovedAuthorityBeforeSending()
    {
        var sent = false;
        var handler = new DelegateHandler(_ =>
        {
            sent = true;
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        var configuration = Configuration(new Dictionary<string, string?> { ["RAG_QUERY_BASE_URL"] = "http://public.example:8081/" });
        var client = new InternalRetrievalClient(new HttpClient(handler), configuration);

        await Assert.ThrowsAsync<InternalRetrievalException>(() => client.RetrieveAsync("question"));

        Assert.False(sent);
    }

    [Fact]
    public async Task RejectsShortInternalTokenBeforeSending()
    {
        var sent = false;
        var client = new InternalRetrievalClient(
            new HttpClient(new DelegateHandler(_ => { sent = true; return new HttpResponseMessage(HttpStatusCode.OK); })),
            Configuration(new Dictionary<string, string?> { ["RAG_INTERNAL_TOKEN"] = "too-short" }));

        await Assert.ThrowsAsync<InternalRetrievalException>(() => client.RetrieveAsync("question"));

        Assert.False(sent);
    }

    private static IConfiguration Configuration(Dictionary<string, string?>? overrides = null)
    {
        var values = new Dictionary<string, string?>
        {
            ["RAG_QUERY_BASE_URL"] = "http://rag-query:8081/",
            ["RAG_QUERY_ALLOWED_AUTHORITIES"] = "rag-query:8081",
            ["RAG_QUERY_TIMEOUT_SECONDS"] = "30",
            ["RAG_INTERNAL_TOKEN"] = InternalToken
        };
        if (overrides is not null)
        {
            foreach (var pair in overrides) values[pair.Key] = pair.Value;
        }
        return new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    }

    private const string ValidResponse = """
        {"source_sufficiency":"partial","requires_limitation":true,"requires_refusal":false,"limitation_reason":"Limited evidence.","citations":[{"document_id":"11111111-1111-1111-1111-111111111111","chunk_id":"22222222-2222-2222-2222-222222222222","title":"Statistik DKI","year":2026,"region":"DKI Jakarta","page_start":1,"page_end":1,"source_url":"https://bps.go.id/source","snippet":"Relevant evidence."}]}
        """;

    private sealed class DelegateHandler(Func<HttpRequestMessage, HttpResponseMessage> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(send(request));
    }
}
