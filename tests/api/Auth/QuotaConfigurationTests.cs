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
            ChatRateLimit.CreatePartition(context, 10, TimeSpan.FromMinutes(1), 1, () => constructions++));
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

}
