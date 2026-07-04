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
}
