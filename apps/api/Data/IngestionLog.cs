using System.Text.Json;

namespace Ringkas.Api.Data;

public sealed class IngestionLog
{
    public Guid Id { get; set; }
    public Guid JobId { get; set; }
    public Guid? DocumentId { get; set; }
    public string Level { get; set; } = null!;
    public string Message { get; set; } = null!;
    public JsonDocument? MetadataJson { get; set; }
    public DateTime CreatedAt { get; set; }
}

public static class IngestionLogLevels
{
    public const string Info = "info";
    public const string Warn = "warn";
    public const string Error = "error";
}
