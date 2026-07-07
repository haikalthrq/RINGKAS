using System.Globalization;
using System.Security.Claims;

namespace Ringkas.Api.Auth;

public static class QuotaConfiguration
{
    public const int DefaultGuestPromptQuota = 1;

    public static int ReadGuestPromptQuota(IConfiguration configuration)
    {
        var value = configuration["GUEST_PROMPT_QUOTA"];
        if (string.IsNullOrWhiteSpace(value))
        {
            return DefaultGuestPromptQuota;
        }

        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var quota) || quota != 1)
        {
            throw new InvalidOperationException("GUEST_PROMPT_QUOTA must be exactly 1.");
        }

        return quota;
    }

    public static int? ReadRegisteredDailyQuota(IConfiguration configuration)
    {
        var value = configuration["REGISTERED_DAILY_QUOTA"];
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var quota) || quota <= 0)
        {
            throw new InvalidOperationException("REGISTERED_DAILY_QUOTA must be blank or a positive integer.");
        }

        return quota;
    }

    public static bool IsQuotaBypassUser(ClaimsPrincipal user) =>
        user.IsInRole(AppRoles.Admin) || user.IsInRole(AppRoles.SystemMaintainer);

    public static string? UserId(ClaimsPrincipal user) => user.FindFirstValue(ClaimTypes.NameIdentifier);
}
