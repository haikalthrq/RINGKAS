namespace Ringkas.Api.Data;

public sealed class Document
{
    public Guid Id { get; set; }
    public string Title { get; set; } = null!;
    public int PublicationYear { get; set; }
    public DateOnly? ReleaseDate { get; set; }
    public string Region { get; set; } = null!;
    public string RegionLevel { get; set; } = null!;
    public string? Topic { get; set; }
    public string? CatalogNumber { get; set; }
    public string? PublicationNumber { get; set; }
    public string SourcePageUrl { get; set; } = null!;
    public string? PdfUrl { get; set; }
    public string? LocalPdfPath { get; set; }
    public string? Language { get; set; }
    public int? PageCount { get; set; }
    public string IngestionStatus { get; set; } = DocumentIngestionStatuses.Pending;
    public string Checksum { get; set; } = null!;
    public DateTime CreatedAt { get; set; }
    public DateTime? IngestedAt { get; set; }
    public string? ErrorMessage { get; set; }
}

public static class DocumentIngestionStatuses
{
    public const string Pending = "pending";
    public const string Downloaded = "downloaded";
    public const string Parsed = "parsed";
    public const string Indexed = "indexed";
    public const string Failed = "failed";
    public const string UnsupportedOrExtractionFailed = "unsupported_or_extraction_failed";
}
