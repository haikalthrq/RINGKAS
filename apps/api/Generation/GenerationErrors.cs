namespace Ringkas.Api.Generation;

public enum GenerationFailureCategory
{
    InvalidRequest,
    InvalidConfiguration,
    AuthenticationOrAuthorization,
    RateLimited,
    Timeout,
    TransportUnavailable,
    ProviderRejection,
    MalformedResponse,
    FallbackExhausted
}

public class GenerationException : Exception
{
    public GenerationException(GenerationFailureCategory category, string message, int? statusCode = null)
        : base(SafeMessage(category))
    {
        Category = category;
        StatusCode = statusCode;
    }

    public GenerationFailureCategory Category { get; }

    public int? StatusCode { get; }

    private static string SafeMessage(GenerationFailureCategory category) => category switch
    {
        GenerationFailureCategory.InvalidRequest => "Generation request is invalid.",
        GenerationFailureCategory.InvalidConfiguration => "Generation provider configuration is invalid.",
        GenerationFailureCategory.AuthenticationOrAuthorization => "Generation provider authorization failed.",
        GenerationFailureCategory.RateLimited => "Generation provider rate limit was reached.",
        GenerationFailureCategory.Timeout => "Generation provider request timed out.",
        GenerationFailureCategory.TransportUnavailable => "Generation provider is unavailable.",
        GenerationFailureCategory.ProviderRejection => "Generation provider rejected the request.",
        GenerationFailureCategory.MalformedResponse => "Generation provider returned an unusable response.",
        GenerationFailureCategory.FallbackExhausted => "Generation is unavailable from configured providers.",
        _ => "Generation failed."
    };
}

public sealed class GenerationFallbackExhaustedException : GenerationException
{
    public GenerationFallbackExhaustedException(
        GenerationFailureCategory primaryFailure,
        GenerationFailureCategory fallbackFailure)
        : base(GenerationFailureCategory.FallbackExhausted, "Generation is unavailable from configured providers.")
    {
        PrimaryFailure = primaryFailure;
        FallbackFailure = fallbackFailure;
    }

    public GenerationFailureCategory PrimaryFailure { get; }

    public GenerationFailureCategory FallbackFailure { get; }
}
