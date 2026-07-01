namespace Ringkas.Api.Generation;

public sealed class FailoverGenerationClient(
    INvidiaNimGenerationClient primary,
    ICloudflareWorkersAiGenerationClient fallback,
    ILogger<FailoverGenerationClient> logger) : IGenerationClient
{
    public async Task<GenerationResult> GenerateAsync(GenerationRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        try
        {
            return await primary.GenerateAsync(request, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (GenerationException primaryFailure) when (IsFallbackEligible(primaryFailure))
        {
            logger.LogInformation(
                "Generation fallback is being attempted after primary failure category {FailureCategory} with status {StatusCode}.",
                primaryFailure.Category,
                primaryFailure.StatusCode);
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                var result = await fallback.GenerateAsync(request, cancellationToken);
                logger.LogInformation("Generation fallback succeeded with provider {Provider}.", result.Provider);
                return result;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (GenerationException fallbackFailure)
            {
                logger.LogInformation(
                    "Generation fallback failed with category {FailureCategory} and status {StatusCode}.",
                    fallbackFailure.Category,
                    fallbackFailure.StatusCode);
                throw new GenerationFallbackExhaustedException(primaryFailure.Category, fallbackFailure.Category);
            }
        }
    }

    private static bool IsFallbackEligible(GenerationException exception) =>
        exception.Category is GenerationFailureCategory.TransportUnavailable or
            GenerationFailureCategory.Timeout or
            GenerationFailureCategory.RateLimited or
            GenerationFailureCategory.MalformedResponse ||
        (exception.Category == GenerationFailureCategory.ProviderRejection && exception.StatusCode is >= 500 and <= 599);
}
