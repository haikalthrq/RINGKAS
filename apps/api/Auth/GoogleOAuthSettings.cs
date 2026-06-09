namespace Ringkas.Api.Auth;

public sealed record GoogleOAuthSettings(string? ClientId, string? ClientSecret)
{
    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(ClientId) &&
        !string.IsNullOrWhiteSpace(ClientSecret);

    public static GoogleOAuthSettings FromConfiguration(IConfiguration configuration) =>
        new(configuration["GOOGLE_CLIENT_ID"], configuration["GOOGLE_CLIENT_SECRET"]);
}
