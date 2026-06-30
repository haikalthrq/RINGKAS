using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;

namespace Ringkas.Api.Endpoints;

public static class DocumentEndpoints
{
    public static IEndpointRouteBuilder MapDocumentEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/documents")
            .RequireAuthorization(AuthorizationPolicies.RegisteredUser);

        group.MapGet("/search", SearchAsync);

        return endpoints;
    }

    private static async Task<IResult> SearchAsync(
        [FromQuery] string? q,
        [FromQuery] int? year,
        [FromQuery] string? topic,
        [FromQuery] int? page,
        [FromQuery(Name = "page_size")] int? pageSize,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var keyword = q?.Trim();
        var topicFilter = topic?.Trim();
        var requestedPage = page ?? 1;
        var requestedPageSize = pageSize ?? 20;

        var errors = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrWhiteSpace(keyword) && year is null && string.IsNullOrWhiteSpace(topicFilter))
        {
            errors["search"] = ["At least one search criterion is required."];
        }

        if (keyword is { Length: > 200 })
        {
            errors["q"] = ["The search keyword is too long."];
        }

        if (topicFilter is { Length: > 200 })
        {
            errors["topic"] = ["The topic filter is too long."];
        }

        if (year is <= 0)
        {
            errors["year"] = ["The publication year must be positive."];
        }

        if (requestedPage <= 0)
        {
            errors["page"] = ["The page must be positive."];
        }

        if (requestedPageSize is < 1 or > 100)
        {
            errors["page_size"] = ["The page size must be between 1 and 100."];
        }

        if (errors.Count > 0)
        {
            return Results.ValidationProblem(errors);
        }

        var escapedKeyword = EscapeLikePattern(keyword);
        var escapedTopic = EscapeLikePattern(topicFilter);
        var skip = ((long)requestedPage - 1) * requestedPageSize;
        if (skip > int.MaxValue)
        {
            return Results.ValidationProblem(new Dictionary<string, string[]>
            {
                ["page"] = ["The requested page is out of range."]
            });
        }

        var query = dbContext.Documents
            .AsNoTracking()
            .Where(document => document.IngestionStatus == DocumentIngestionStatuses.Indexed);

        if (!string.IsNullOrWhiteSpace(keyword))
        {
            var pattern = $"%{escapedKeyword}%";
            query = query.Where(document =>
                EF.Functions.ILike(document.Title, pattern, "\\") ||
                (document.Topic != null && EF.Functions.ILike(document.Topic, pattern, "\\")) ||
                (document.CatalogNumber != null && EF.Functions.ILike(document.CatalogNumber, pattern, "\\")) ||
                (document.PublicationNumber != null && EF.Functions.ILike(document.PublicationNumber, pattern, "\\")));
        }

        if (year.HasValue)
        {
            query = query.Where(document => document.PublicationYear == year.Value);
        }

        if (!string.IsNullOrWhiteSpace(topicFilter))
        {
            query = query.Where(document =>
                document.Topic != null && EF.Functions.ILike(document.Topic, $"%{escapedTopic}%", "\\"));
        }

        var totalCount = await query.CountAsync(cancellationToken);
        var items = await query
            .OrderByDescending(document => document.PublicationYear)
            .ThenBy(document => document.Title)
            .ThenBy(document => document.Id)
            .Skip((int)skip)
            .Take(requestedPageSize)
            .Select(document => new DocumentSearchItem(
                document.Id,
                document.Title,
                document.PublicationYear,
                document.Region,
                document.RegionLevel,
                document.Topic,
                document.SourcePageUrl,
                document.PdfUrl))
            .ToListAsync(cancellationToken);

        return Results.Ok(new DocumentSearchResponse(requestedPage, requestedPageSize, totalCount, items));
    }

    private static string? EscapeLikePattern(string? value) =>
        value?.Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("%", "\\%", StringComparison.Ordinal)
            .Replace("_", "\\_", StringComparison.Ordinal);
}

public sealed record DocumentSearchResponse(
    int Page,
    int PageSize,
    int TotalCount,
    IReadOnlyList<DocumentSearchItem> Items);

public sealed record DocumentSearchItem(
    Guid DocumentId,
    string Title,
    int PublicationYear,
    string Region,
    string RegionLevel,
    string? Topic,
    string SourcePageUrl,
    string? PdfUrl);
