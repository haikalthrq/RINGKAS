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
}
