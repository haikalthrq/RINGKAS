namespace Ringkas.Api.Auth;

public static class AppRoles
{
    public const string Guest = "guest";
    public const string User = "user";
    public const string Admin = "admin";
    public const string SystemMaintainer = "system_maintainer";

    public static readonly string[] All = [Guest, User, Admin, SystemMaintainer];
}
