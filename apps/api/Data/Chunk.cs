namespace Ringkas.Api.Data;

public sealed class Chunk
{
    public Guid Id { get; set; }
    public Guid DocumentId { get; set; }
    public int ChunkIndex { get; set; }
    public string Text { get; set; } = null!;
    public int? PageStart { get; set; }
    public int? PageEnd { get; set; }
    public string? SectionHeading { get; set; }
    public string ExtractionMethod { get; set; } = null!;
    public bool LowStructureConfidence { get; set; }
    public string SourceUrl { get; set; } = null!;
    public string QdrantPointId { get; set; } = null!;
    public DateTime CreatedAt { get; set; }
}
