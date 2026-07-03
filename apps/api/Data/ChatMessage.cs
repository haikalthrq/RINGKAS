using System.Text.Json;

namespace Ringkas.Api.Data;

public sealed class ChatMessage
{
    public Guid Id { get; set; }
    public Guid SessionId { get; set; }
    public string Role { get; set; } = null!;
    public string Content { get; set; } = null!;
    public JsonDocument? CitationsJson { get; set; }
    public string? Provider { get; set; }
    public DateTime CreatedAt { get; set; }
}

public static class ChatMessageRoles
{
    public const string User = "user";
    public const string Assistant = "assistant";
    public const string System = "system";
}

public static class ChatMessageProviders
{
    public const string NvidiaNim = "nvidia_nim";
    public const string CloudflareWorkersAi = "cloudflare_workers_ai";
}
