namespace Ringkas.Api.Auth;

public sealed record RegisterRequest(string? Email, string? Password);

public sealed record LoginRequest(string? Email, string? Password);

public sealed record CurrentUserResponse(
    bool Authenticated,
    string? Id,
    string? Email,
    bool EmailConfirmed,
    IReadOnlyList<string> Roles);
