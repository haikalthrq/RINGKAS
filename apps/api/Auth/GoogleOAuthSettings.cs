namespace Ringkas.Api.Auth;

public sealed record GoogleOAuthSettings(string? ClientId, string? ClientSecret)
{
    // The web app only proxies /api/*, so the provider callback must stay on that path.
    public const string ProviderCallbackPath = "/api/auth/google/provider-callback";
    public const string EmailVerifiedClaimType = "urn:google:email_verified";

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(ClientId) &&
        !string.IsNullOrWhiteSpace(ClientSecret);

    public static GoogleOAuthSettings FromConfiguration(IConfiguration configuration) =>
        new(configuration["GOOGLE_CLIENT_ID"], configuration["GOOGLE_CLIENT_SECRET"]);
}
