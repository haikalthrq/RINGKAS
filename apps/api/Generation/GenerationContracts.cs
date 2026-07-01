using System.Collections.Immutable;
using Microsoft.Extensions.DependencyInjection;

namespace Ringkas.Api.Generation;

public enum GenerationRole
{
    System,
    User,
    Assistant
}

public enum GenerationProvider
{
    NvidiaNim,
    CloudflareWorkersAi
}

public sealed record GenerationMessage(GenerationRole Role, string Content)
{
    public override string ToString() => $"GenerationMessage {{ Role = {Role}, Content = [REDACTED] }}";
}

public sealed class GenerationRequest
{
    public GenerationRequest(IEnumerable<GenerationMessage> messages)
    {
        ArgumentNullException.ThrowIfNull(messages);
        Messages = messages.ToImmutableArray();

        if (Messages.IsDefaultOrEmpty)
        {
            throw new GenerationException(GenerationFailureCategory.InvalidRequest, "Generation request messages are required.");
        }

        if (Messages.Any(message => message is null || !Enum.IsDefined(message.Role) || string.IsNullOrWhiteSpace(message.Content)))
        {
            throw new GenerationException(GenerationFailureCategory.InvalidRequest, "Generation messages must have a supported role and nonblank content.");
        }
    }

    public ImmutableArray<GenerationMessage> Messages { get; }

    public override string ToString() => $"GenerationRequest {{ MessageCount = {Messages.Length} }}";
}

public sealed class GenerationUsage
{
    public GenerationUsage(int? promptTokens = null, int? completionTokens = null, int? totalTokens = null)
    {
        if (new[] { promptTokens, completionTokens, totalTokens }.Any(value => value is < 0))
        {
            throw new GenerationException(GenerationFailureCategory.MalformedResponse, "Generation usage values must be nonnegative.");
        }

        PromptTokens = promptTokens;
        CompletionTokens = completionTokens;
        TotalTokens = totalTokens;
    }

    public int? PromptTokens { get; }

    public int? CompletionTokens { get; }

    public int? TotalTokens { get; }

    public override string ToString() => "GenerationUsage { [REDACTED] }";
}

public sealed class GenerationResult
{
    public GenerationResult(string text, GenerationProvider provider, string model, GenerationUsage? usage = null)
    {
        if (string.IsNullOrWhiteSpace(text) || string.IsNullOrWhiteSpace(model) || !Enum.IsDefined(provider))
        {
            throw new GenerationException(GenerationFailureCategory.MalformedResponse, "Generation result is invalid.");
        }

        Text = text;
        Provider = provider;
        Model = model;
        Usage = usage;
    }

    public string Text { get; }

    public GenerationProvider Provider { get; }

    public string Model { get; }

    public GenerationUsage? Usage { get; }

    public override string ToString() => $"GenerationResult {{ Provider = {Provider}, Model = {Model}, Text = [REDACTED] }}";
}

public interface IGenerationClient
{
    Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default);
}

public interface INvidiaNimGenerationClient : IGenerationClient;

public interface ICloudflareWorkersAiGenerationClient : IGenerationClient;

public static class GenerationServiceCollectionExtensions
{
    public static IServiceCollection AddGenerationClients(this IServiceCollection services)
    {
        services.AddHttpClient<INvidiaNimGenerationClient, NvidiaNimGenerationClient>(client =>
            client.Timeout = Timeout.InfiniteTimeSpan);
        services.AddHttpClient<ICloudflareWorkersAiGenerationClient, CloudflareWorkersAiGenerationClient>(client =>
            client.Timeout = Timeout.InfiniteTimeSpan);
        services.AddTransient<IGenerationClient, FailoverGenerationClient>();
        return services;
    }
}
