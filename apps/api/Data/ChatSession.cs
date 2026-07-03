namespace Ringkas.Api.Data;

public sealed class ChatSession
{
    public Guid Id { get; set; }
    public string UserId { get; set; } = null!;
    public string? Title { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
}
