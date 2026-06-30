using Microsoft.EntityFrameworkCore;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;

namespace Ringkas.Api.Endpoints;

public static class SourceEndpoints
{
    public static IEndpointRouteBuilder MapSourceEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/sources")
            .RequireAuthorization(AuthorizationPolicies.RegisteredUser);

        group.MapGet("/chunks/{chunkId:guid}", GetChunkSourceAsync);
        group.MapGet("/documents/{documentId:guid}", GetDocumentSourceAsync);

        return endpoints;
    }

    private static async Task<IResult> GetChunkSourceAsync(
        Guid chunkId,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var source = await (
            from chunk in dbContext.Chunks.AsNoTracking()
            join document in dbContext.Documents.AsNoTracking()
                on chunk.DocumentId equals document.Id
            where chunk.Id == chunkId && document.IngestionStatus == DocumentIngestionStatuses.Indexed
            select new ChunkSourceResponse(
                chunk.Id,
                document.Id,
                document.Title,
                document.PublicationYear,
                document.Region,
                document.RegionLevel,
                document.Topic,
                chunk.PageStart,
                chunk.PageEnd,
                chunk.SectionHeading,
                chunk.SourceUrl,
                document.PdfUrl,
                chunk.Text))
            .SingleOrDefaultAsync(cancellationToken);

        return source is null ? Results.NotFound() : Results.Ok(source);
    }

    private static async Task<IResult> GetDocumentSourceAsync(
        Guid documentId,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var source = await dbContext.Documents
            .AsNoTracking()
            .Where(document =>
                document.Id == documentId &&
                document.IngestionStatus == DocumentIngestionStatuses.Indexed)
            .Select(document => new DocumentSourceResponse(
                document.Id,
                document.Title,
                document.PublicationYear,
                document.ReleaseDate,
                document.Region,
                document.RegionLevel,
                document.Topic,
                document.CatalogNumber,
                document.PublicationNumber,
                document.SourcePageUrl,
                document.PdfUrl,
                document.Language,
                document.PageCount))
            .SingleOrDefaultAsync(cancellationToken);

        return source is null ? Results.NotFound() : Results.Ok(source);
    }
}

public sealed record ChunkSourceResponse(
    Guid ChunkId,
    Guid DocumentId,
    string DocumentTitle,
    int PublicationYear,
    string Region,
    string RegionLevel,
    string? Topic,
    int? PageStart,
    int? PageEnd,
    string? SectionHeading,
    string SourceUrl,
    string? PdfUrl,
    string Excerpt);

public sealed record DocumentSourceResponse(
    Guid DocumentId,
    string Title,
    int PublicationYear,
    DateOnly? ReleaseDate,
    string Region,
    string RegionLevel,
    string? Topic,
    string? CatalogNumber,
    string? PublicationNumber,
    string SourcePageUrl,
    string? PdfUrl,
    string? Language,
    int? PageCount);
