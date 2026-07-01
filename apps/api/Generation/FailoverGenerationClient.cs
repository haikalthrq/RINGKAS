namespace Ringkas.Api.Generation;

public sealed class FailoverGenerationClient(
    INvidiaNimGenerationClient primary,
    ICloudflareWorkersAiGenerationClient fallback,
    ILogger<FailoverGenerationClient> logger,
    IConfiguration? configuration = null) : IGenerationClient
{
    public async Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();

        var attempts = new List<(IGenerationClient Client, string? Model)>
        {
            (primary, null),
            (fallback, null)
        };
        AddConfiguredAttempt(attempts, primary, "NVIDIA_NIM_GENERATION_SECONDARY_MODEL");
        AddConfiguredAttempt(attempts, primary, "NVIDIA_NIM_GENERATION_LIGHTWEIGHT_MODEL");
        AddConfiguredAttempt(attempts, fallback, "CLOUDFLARE_WORKERS_AI_EXPERIMENTAL_MODEL");

        GenerationException? firstFailure = null;
        GenerationException? lastFailure = null;
        for (var index = 0; index < attempts.Count; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var attempt = attempts[index];
            try
            {
                return attempt.Model is null
                    ? await attempt.Client.GenerateAsync(request, cancellationToken)
                    : await ((IModelOverrideGenerationClient)attempt.Client).GenerateWithModelAsync(request, attempt.Model, cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (GenerationException failure) when (firstFailure is null && !IsFallbackEligible(failure))
            {
                throw;
            }
            catch (GenerationException failure) when (IsFallbackEligible(failure))
            {
                firstFailure ??= failure;
                lastFailure = failure;
                logger.LogInformation(
                    "Generation attempt failed with failure category {FailureCategory} and status {StatusCode}; trying the next configured provider {NextProvider}.",
                    failure.Category,
                    failure.StatusCode,
                    index + 1 < attempts.Count
                        ? attempts[index + 1].Client is INvidiaNimGenerationClient ? GenerationProvider.NvidiaNim : GenerationProvider.CloudflareWorkersAi
                        : attempt.Client is INvidiaNimGenerationClient ? GenerationProvider.NvidiaNim : GenerationProvider.CloudflareWorkersAi);
            }
            catch (GenerationException failure) when (firstFailure is not null)
            {
                lastFailure = failure;
                break;
            }
        }

        if (firstFailure is not null && lastFailure is not null)
        {
            throw new GenerationFallbackExhaustedException(firstFailure.Category, lastFailure.Category);
        }

        throw new GenerationException(GenerationFailureCategory.InvalidConfiguration, "Generation provider configuration is invalid.");
    }

    private string? ReadModel(string key)
    {
        var model = configuration?[key];
        return string.IsNullOrWhiteSpace(model) || model.Any(char.IsWhiteSpace) ? null : model;
    }

    private void AddConfiguredAttempt(
        ICollection<(IGenerationClient Client, string? Model)> attempts,
        IGenerationClient client,
        string key)
    {
        var model = ReadModel(key);
        if (model is not null && client is IModelOverrideGenerationClient)
        {
            attempts.Add((client, model));
        }
    }

    private static bool IsFallbackEligible(GenerationException exception) =>
        exception.Category is GenerationFailureCategory.TransportUnavailable or
            GenerationFailureCategory.Timeout or
            GenerationFailureCategory.RateLimited or
            GenerationFailureCategory.MalformedResponse ||
        (exception.Category == GenerationFailureCategory.ProviderRejection && exception.StatusCode is >= 500 and <= 599);
}
