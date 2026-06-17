namespace Ringkas.Api.Data;

public sealed class IngestionJob
{
    public Guid Id { get; set; }
    public string RequestedByUserId { get; set; } = null!;
    public string Status { get; set; } = IngestionJobStatuses.Queued;
    public string ScopeRegion { get; set; } = null!;
    public int ScopeYearStart { get; set; }
    public int ScopeYearEnd { get; set; }
    public int MaxDocuments { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public DateTime CreatedAt { get; set; }
    public string? ErrorSummary { get; set; }
}

public static class IngestionJobStatuses
{
    public const string Queued = "queued";
    public const string Running = "running";
    public const string Completed = "completed";
    public const string Failed = "failed";
    public const string Cancelled = "cancelled";
}
