using System.Security.Claims;
using System.Net;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Ringkas.Api.Auth;

namespace Ringkas.Api.Tests.Auth;

public sealed class QuotaConfigurationTests
{
    [Fact]
    public void GuestQuotaDefaultsToAndAcceptsExactlyOne()
    {
        Assert.Equal(1, QuotaConfiguration.ReadGuestPromptQuota(Configuration()));
        Assert.Equal(1, QuotaConfiguration.ReadGuestPromptQuota(Configuration(("GUEST_PROMPT_QUOTA", "1"))));
    }

    [Theory]
    [InlineData("0")]
    [InlineData("2")]
    [InlineData("unsafe")]
    public void GuestQuotaRejectsUnsafeValues(string value)
    {
        Assert.Throws<InvalidOperationException>(() =>
            QuotaConfiguration.ReadGuestPromptQuota(Configuration(("GUEST_PROMPT_QUOTA", value))));
    }

    [Fact]
    public async Task GuestGetsOnePermitAndLimiterIsConstructedOncePerIp()
    {
        var constructions = 0;
        using var limiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
            ChatRateLimit.CreatePartition(context, 10, TimeSpan.FromMinutes(1), 1, null, () => constructions++));
        var firstIp = Guest("192.0.2.1");
        var secondIp = Guest("192.0.2.2");

        using var first = limiter.AttemptAcquire(firstIp);
        using var rejected = await limiter.AcquireAsync(firstIp);
        using var otherPartition = limiter.AttemptAcquire(secondIp);

        Assert.True(first.IsAcquired);
        Assert.False(rejected.IsAcquired);
        Assert.True(otherPartition.IsAcquired);
        Assert.Equal(2, constructions);
    }

    [Fact]
    public void RegisteredQuotaBlankDisablesAndPositiveValueEnables()
    {
        Assert.Null(QuotaConfiguration.ReadRegisteredDailyQuota(Configuration()));
        Assert.Equal(7, QuotaConfiguration.ReadRegisteredDailyQuota(Configuration(("REGISTERED_DAILY_QUOTA", "7"))));
    }

    [Theory]
    [InlineData("0")]
    [InlineData("-1")]
    [InlineData("unsafe")]
    public void RegisteredQuotaRejectsInvalidNonblankValues(string value)
    {
        Assert.Throws<InvalidOperationException>(() =>
            QuotaConfiguration.ReadRegisteredDailyQuota(Configuration(("REGISTERED_DAILY_QUOTA", value))));
    }

    [Fact]
    public void AdminAndSystemMaintainerBypassOnlyRegisteredQuota()
    {
        Assert.True(QuotaConfiguration.IsQuotaBypassUser(UserWithRole(AppRoles.Admin)));
        Assert.True(QuotaConfiguration.IsQuotaBypassUser(UserWithRole(AppRoles.SystemMaintainer)));
        Assert.False(QuotaConfiguration.IsQuotaBypassUser(UserWithRole(AppRoles.User)));
    }

    [Fact]
    public async Task RegisteredUserHonorsConfiguredDailyQuota()
    {
        using var limiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
            ChatRateLimit.CreatePartition(context, 10, TimeSpan.FromMinutes(1), 1, 2));
        var user = Authenticated(AppRoles.User);

        using var first = limiter.AttemptAcquire(user);
        using var second = await limiter.AcquireAsync(user);
        using var rejected = limiter.AttemptAcquire(user);

        Assert.True(first.IsAcquired);
        Assert.True(second.IsAcquired);
        Assert.False(rejected.IsAcquired);
    }

    [Fact]
    public async Task AdminBypassesDailyQuotaButKeepsThreePerWindowLimit()
    {
        using var limiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
            ChatRateLimit.CreatePartition(context, 3, TimeSpan.FromMinutes(1), 1, 1));
        var admin = Authenticated(AppRoles.Admin);

        using var first = limiter.AttemptAcquire(admin);
        using var second = await limiter.AcquireAsync(admin);
        using var third = limiter.AttemptAcquire(admin);
        using var rejected = await limiter.AcquireAsync(admin);

        Assert.True(first.IsAcquired);
        Assert.True(second.IsAcquired);
        Assert.True(third.IsAcquired);
        Assert.False(rejected.IsAcquired);
    }

    private static IConfiguration Configuration(params (string Key, string Value)[] values) =>
        new ConfigurationBuilder()
            .AddInMemoryCollection(values.ToDictionary(value => value.Key, value => (string?)value.Value))
            .Build();

    private static DefaultHttpContext Guest(string address)
    {
        var context = new DefaultHttpContext();
        context.Connection.RemoteIpAddress = IPAddress.Parse(address);
        return context;
    }

    private static ClaimsPrincipal UserWithRole(string role) => new(new ClaimsIdentity(
        [new Claim(ClaimTypes.Role, role), new Claim(ClaimTypes.NameIdentifier, "user-1")], "test"));

    private static DefaultHttpContext Authenticated(string role)
    {
        var context = new DefaultHttpContext { User = UserWithRole(role) };
        return context;
    }

}
