using System.Security.Claims;
using Microsoft.Extensions.Configuration;
using Ringkas.Api.Auth;
using Ringkas.Api.Endpoints;

namespace Ringkas.Api.Tests.Auth;

public sealed class GoogleOAuthTests
{
    [Fact]
    public void GoogleConfigurationRequiresBothCredentials()
    {
        Assert.False(GoogleOAuthSettings.FromConfiguration(Configuration()).IsConfigured);
        Assert.False(GoogleOAuthSettings.FromConfiguration(Configuration(("GOOGLE_CLIENT_ID", "client"))).IsConfigured);
        Assert.True(GoogleOAuthSettings.FromConfiguration(Configuration(
            ("GOOGLE_CLIENT_ID", "client"),
            ("GOOGLE_CLIENT_SECRET", "secret"))).IsConfigured);
    }

    [Theory]
    [InlineData("/chat", true)]
    [InlineData("/documents?year=2024", true)]
    [InlineData("https://evil.example", false)]
    [InlineData("//evil.example", false)]
    [InlineData("/\\evil.example", false)]
    [InlineData("/chat\\evil", false)]
    [InlineData("/chat?next=https://evil.example", false)]
    public void ReturnUrlMustBeSameOriginAndLocal(string returnUrl, bool expected)
    {
        Assert.Equal(expected, AuthEndpoints.IsLocalReturnUrl(returnUrl));
    }

    [Fact]
    public void InvalidReturnUrlFallsBackToChat()
    {
        Assert.Equal("/chat", AuthEndpoints.GetSafeReturnUrl("https://evil.example"));
        Assert.Equal("/documents", AuthEndpoints.GetSafeReturnUrl("/documents"));
    }

    [Theory]
    [InlineData("email_verified", "true", true)]
    [InlineData("verified_email", "True", true)]
    [InlineData("email_verified", "false", false)]
    public void GoogleEmailMustBeProviderVerified(string claimType, string value, bool expected)
    {
        var principal = new ClaimsPrincipal(new ClaimsIdentity([new Claim(claimType, value)], "Google"));

        Assert.Equal(expected, AuthEndpoints.IsGoogleEmailVerified(principal));
    }

    private static IConfiguration Configuration(params (string Key, string Value)[] values) =>
        new ConfigurationBuilder()
            .AddInMemoryCollection(values.ToDictionary(value => value.Key, value => (string?)value.Value))
            .Build();
}
