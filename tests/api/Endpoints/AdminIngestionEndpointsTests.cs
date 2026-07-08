using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Infrastructure;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;
using Ringkas.Api.Endpoints;

namespace Ringkas.Api.Tests.Endpoints;

public sealed class AdminIngestionEndpointsTests
{
    [Fact]
    public void ValidateAcceptsDocumentedRequest()
    {
        var request = new CreateIngestionJobRequest("DKI Jakarta", 2022, 2026, 300);

        Assert.Empty(request.Validate());
    }

    [Fact]
    public void ValidateRejectsForceReprocessAndInvalidWorkerScope()
    {
        var request = new CreateIngestionJobRequest("Jawa Barat", 2026, 2022, 301, true);

        var errors = request.Validate();

        Assert.Equal(["region", "year_end", "max_documents", "force_reprocess"], errors.Keys);
        Assert.Contains("not supported", errors["force_reprocess"][0], StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SanitizeForAdminBoundsSafeTextAndRedactsSensitiveDetails()
    {
        Assert.Equal("safe sum", AdminIngestionEndpoints.SanitizeForAdmin("  safe\r\n sum  ", "withheld", 20));
        Assert.Equal("12345", AdminIngestionEndpoints.SanitizeForAdmin("123456", "withheld", 5));
        Assert.Equal("withheld", AdminIngestionEndpoints.SanitizeForAdmin("Bearer secret-token", "withheld", 20));
        Assert.Null(AdminIngestionEndpoints.SanitizeForAdmin(" ", "withheld", 20));
    }

    [Fact]
    public void GetAndPostRoutesInheritAdminAuthorizationAndRateLimit()
    {
        var builder = WebApplication.CreateBuilder();
        builder.Services.AddScoped<RingkasDbContext>();
        var app = builder.Build();
        app.MapAdminIngestionEndpoints();

        var routes = ((IEndpointRouteBuilder)app).DataSources
            .SelectMany(source => source.Endpoints)
            .OfType<RouteEndpoint>()
            .Where(route => route.RoutePattern.RawText?.StartsWith("/api/admin/ingestion/jobs", StringComparison.Ordinal) == true)
            .ToArray();

        Assert.Equal(2, routes.Length);
        foreach (var route in routes)
        {
            var authorization = route.Metadata.GetMetadata<AuthorizationPolicy>();
            Assert.NotNull(authorization);
            var roles = Assert.Single(authorization!.Requirements.OfType<RolesAuthorizationRequirement>()).AllowedRoles;
            Assert.Contains(AppRoles.Admin, roles);
            Assert.Contains(AppRoles.SystemMaintainer, roles);
            Assert.Equal(RateLimitPolicies.AdminIngestion, route.Metadata.GetMetadata<EnableRateLimitingAttribute>()?.PolicyName);
        }
    }
}
