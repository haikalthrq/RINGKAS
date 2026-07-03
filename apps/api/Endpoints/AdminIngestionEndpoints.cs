using System.Security.Claims;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.RateLimiting;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;

namespace Ringkas.Api.Endpoints;

public static class AdminIngestionEndpoints
{
    public static IEndpointRouteBuilder MapAdminIngestionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/admin/ingestion")
            .RequireAuthorization(policy => policy.RequireRole(AppRoles.Admin, AppRoles.SystemMaintainer))
            .RequireRateLimiting(RateLimitPolicies.AdminIngestion);

        group.MapPost("/jobs", CreateJobAsync);

        return endpoints;
    }

    private static async Task<IResult> CreateJobAsync(
        CreateIngestionJobRequest request,
        ClaimsPrincipal user,
        RingkasDbContext dbContext,
        CancellationToken cancellationToken)
    {
        var errors = request.Validate();
        if (errors.Count > 0)
        {
            return Results.ValidationProblem(errors);
        }

        var userId = user.FindFirstValue(ClaimTypes.NameIdentifier);
        if (string.IsNullOrWhiteSpace(userId))
        {
            return Results.Unauthorized();
        }

        var job = new IngestionJob
        {
            Id = Guid.NewGuid(),
            RequestedByUserId = userId,
            Status = IngestionJobStatuses.Queued,
            ScopeRegion = CreateIngestionJobRequest.MvpRegion,
            ScopeYearStart = request.YearStart,
            ScopeYearEnd = request.YearEnd,
            MaxDocuments = request.MaxDocuments,
            CreatedAt = DateTime.UtcNow
        };

        dbContext.IngestionJobs.Add(job);
        await dbContext.SaveChangesAsync(cancellationToken);

        var response = new CreateIngestionJobResponse(
            job.Id,
            job.Status,
            job.ScopeRegion,
            job.ScopeYearStart,
            job.ScopeYearEnd,
            job.MaxDocuments,
            job.CreatedAt);
        return Results.Created($"/api/admin/ingestion/jobs/{job.Id}", response);
    }
}

public sealed record CreateIngestionJobRequest(
    string? Region,
    [property: JsonPropertyName("year_start")] int YearStart,
    [property: JsonPropertyName("year_end")] int YearEnd,
    [property: JsonPropertyName("max_documents")] int MaxDocuments,
    [property: JsonPropertyName("force_reprocess")] bool ForceReprocess = false)
{
    public const string MvpRegion = "DKI Jakarta";

    public Dictionary<string, string[]> Validate()
    {
        var errors = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrWhiteSpace(Region))
        {
            errors["region"] = ["Region is required."];
        }
        else if (Region.Trim().Length > 200)
        {
            errors["region"] = ["Region must not exceed 200 characters."];
        }
        else if (!string.Equals(Region.Trim(), MvpRegion, StringComparison.OrdinalIgnoreCase))
        {
            errors["region"] = [$"Region must be {MvpRegion} for the MVP corpus."];
        }

        if (YearStart <= 0)
        {
            errors["year_start"] = ["Year start must be positive."];
        }

        if (YearEnd <= 0)
        {
            errors["year_end"] = ["Year end must be positive."];
        }
        else if (YearStart > YearEnd)
        {
            errors["year_end"] = ["Year end must be greater than or equal to year start."];
        }

        if (MaxDocuments is < 1 or > 300)
        {
            errors["max_documents"] = ["Max documents must be between 1 and 300."];
        }

        if (ForceReprocess)
        {
            errors["force_reprocess"] = ["Force reprocessing is not supported in the MVP."];
        }

        return errors;
    }
}

public sealed record CreateIngestionJobResponse(
    Guid JobId,
    string Status,
    string Region,
    int YearStart,
    int YearEnd,
    int MaxDocuments,
    DateTime CreatedAt);
