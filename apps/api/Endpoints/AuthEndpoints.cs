using System.Security.Claims;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Google;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.WebUtilities;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;

namespace Ringkas.Api.Endpoints;

public static class AuthEndpoints
{
    public static IEndpointRouteBuilder MapAuthEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/auth");
        group.RequireRateLimiting(RateLimitPolicies.Auth);

        group.MapPost("/register", RegisterAsync).AllowAnonymous();
        group.MapPost("/login", LoginAsync).AllowAnonymous();
        group.MapPost("/logout", LogoutAsync).AllowAnonymous().DisableRateLimiting();
        group.MapGet("/me", MeAsync).AllowAnonymous().DisableRateLimiting();
        group.MapPost("/email-verification/request", RequestEmailVerificationAsync).AllowAnonymous();
        group.MapPost("/email-verification/confirm", ConfirmEmailVerificationAsync).AllowAnonymous();
        group.MapGet("/google", GoogleOAuthStartAsync).AllowAnonymous().DisableRateLimiting();
        group.MapGet("/google/callback", GoogleOAuthCallbackAsync).AllowAnonymous().DisableRateLimiting();

        return endpoints;
    }

    private static async Task<IResult> LogoutAsync(SignInManager<ApplicationUser> signInManager)
    {
        await signInManager.SignOutAsync();
        return Results.Ok(new { message = "Logged out successfully." });
    }

    private static async Task<IResult> RegisterAsync(
        RegisterRequest request,
        UserManager<ApplicationUser> userManager,
        SignInManager<ApplicationUser> signInManager)
    {
        var email = request.Email?.Trim();
        var password = request.Password;

        if (string.IsNullOrWhiteSpace(email) || string.IsNullOrWhiteSpace(password))
        {
            return Results.ValidationProblem(new Dictionary<string, string[]>
            {
                [nameof(request.Email)] = ["Email is required."],
                [nameof(request.Password)] = ["Password is required."]
            });
        }

        var user = new ApplicationUser
        {
            Email = email,
            UserName = email
        };

        var createResult = await userManager.CreateAsync(user, password);
        if (!createResult.Succeeded)
        {
            return Results.ValidationProblem(createResult.ToDictionary());
        }

        var roleResult = await userManager.AddToRoleAsync(user, AppRoles.User);
        if (!roleResult.Succeeded)
        {
            await userManager.DeleteAsync(user);

            return Results.Problem(
                title: "Registration failed.",
                detail: "The account could not be completed.",
                statusCode: StatusCodes.Status500InternalServerError);
        }

        await signInManager.SignInAsync(user, isPersistent: false);

        return Results.Ok(await BuildCurrentUserResponseAsync(userManager, user, authenticated: true));
    }

    private static async Task<IResult> RequestEmailVerificationAsync(
        HttpContext httpContext,
        UserManager<ApplicationUser> userManager)
    {
        var user = await GetCurrentUserAsync(httpContext, userManager);
        if (user is null)
        {
            return Results.Unauthorized();
        }

        if (user.EmailConfirmed)
        {
            return Results.Ok(new
            {
                message = "Email is already verified.",
                emailConfirmed = true
            });
        }

        return Results.Problem(
            title: "Email verification placeholder.",
            detail: "Email verification delivery is not implemented in this MVP placeholder.",
            statusCode: StatusCodes.Status501NotImplemented);
    }

    private static async Task<IResult> ConfirmEmailVerificationAsync(
        HttpContext httpContext,
        UserManager<ApplicationUser> userManager)
    {
        var user = await GetCurrentUserAsync(httpContext, userManager);
        if (user is null)
        {
            return Results.Unauthorized();
        }

        return Results.Problem(
            title: "Email verification placeholder.",
            detail: "Email verification confirmation is not implemented in this MVP placeholder.",
            statusCode: StatusCodes.Status501NotImplemented);
    }

    private static async Task<IResult> GoogleOAuthStartAsync(
        HttpContext httpContext,
        GoogleOAuthSettings googleOAuthSettings,
        SignInManager<ApplicationUser> signInManager)
    {
        var returnUrl = GetSafeReturnUrl(httpContext.Request.Query["returnUrl"].ToString());
        if (!googleOAuthSettings.IsConfigured)
        {
            return GoogleOAuthErrorRedirect(returnUrl, "disabled");
        }

        var callbackUrl = QueryHelpers.AddQueryString("/api/auth/google/callback", "returnUrl", returnUrl);
        var properties = signInManager.ConfigureExternalAuthenticationProperties(
            GoogleDefaults.AuthenticationScheme,
            callbackUrl);

        await httpContext.ChallengeAsync(
            GoogleDefaults.AuthenticationScheme,
            properties);

        return Results.Empty;
    }

    private static async Task<IResult> GoogleOAuthCallbackAsync(
        HttpContext httpContext,
        string? returnUrl,
        string? remoteError,
        GoogleOAuthSettings googleOAuthSettings,
        UserManager<ApplicationUser> userManager,
        SignInManager<ApplicationUser> signInManager,
        ILoggerFactory loggerFactory)
    {
        var logger = loggerFactory.CreateLogger("GoogleOAuthCallback");
        var safeReturnUrl = GetSafeReturnUrl(returnUrl);
        if (!googleOAuthSettings.IsConfigured)
        {
            return GoogleOAuthErrorRedirect(safeReturnUrl, "disabled");
        }
        var providerError = remoteError ?? httpContext.Request.Query["error"].ToString();
        if (!string.IsNullOrWhiteSpace(providerError))
        {
            logger.LogWarning("Google OAuth provider error: {Error}", providerError);
            return GoogleOAuthErrorRedirect(safeReturnUrl, "provider_error");
        }

        var externalLoginInfo = await signInManager.GetExternalLoginInfoAsync();
        if (externalLoginInfo is null)
        {
            var authResult = await httpContext.AuthenticateAsync(IdentityConstants.ExternalScheme);
            if (authResult.Succeeded && authResult.Principal is not null)
            {
                var providerKey = authResult.Principal.FindFirstValue(ClaimTypes.NameIdentifier) ??
                                  authResult.Principal.FindFirstValue("sub") ??
                                  authResult.Principal.FindFirstValue("id");
                if (!string.IsNullOrWhiteSpace(providerKey))
                {
                    logger.LogInformation("Constructed ExternalLoginInfo from AuthenticateAsync fallback with providerKey: {Key}", providerKey);
                    externalLoginInfo = new ExternalLoginInfo(
                        authResult.Principal,
                        GoogleDefaults.AuthenticationScheme,
                        providerKey,
                        GoogleDefaults.DisplayName);
                }
            }
        }

        if (externalLoginInfo is null ||
            !string.Equals(externalLoginInfo.LoginProvider, GoogleDefaults.AuthenticationScheme, StringComparison.Ordinal))
        {
            logger.LogWarning("External login info missing or provider mismatch after fallback. Provider: {Provider}", externalLoginInfo?.LoginProvider);
            return GoogleOAuthErrorRedirect(safeReturnUrl, "login_failed");
        }

        var signInResult = await signInManager.ExternalLoginSignInAsync(
            externalLoginInfo.LoginProvider,
            externalLoginInfo.ProviderKey,
            isPersistent: false,
            bypassTwoFactor: true);

        if (signInResult.Succeeded)
        {
            return Results.LocalRedirect(safeReturnUrl);
        }

        if (signInResult.IsLockedOut || signInResult.IsNotAllowed || signInResult.RequiresTwoFactor)
        {
            return GoogleOAuthErrorRedirect(safeReturnUrl, "account_unavailable");
        }

        var email = (externalLoginInfo.Principal.FindFirstValue(ClaimTypes.Email) ??
            externalLoginInfo.Principal.FindFirstValue("email"))?.Trim();
        if (string.IsNullOrWhiteSpace(email))
        {
            return GoogleOAuthErrorRedirect(safeReturnUrl, "email_missing");
        }

        if (!IsGoogleEmailVerified(externalLoginInfo.Principal))
        {
            return GoogleOAuthErrorRedirect(safeReturnUrl, "email_unverified");
        }

        var existingUser = await userManager.FindByEmailAsync(email);
        if (existingUser is not null)
        {
            var logins = await userManager.GetLoginsAsync(existingUser);
            if (!logins.Any(l => string.Equals(l.LoginProvider, externalLoginInfo.LoginProvider, StringComparison.Ordinal)))
            {
                var addLoginResult = await userManager.AddLoginAsync(
                    existingUser,
                    new UserLoginInfo(
                        externalLoginInfo.LoginProvider,
                        externalLoginInfo.ProviderKey,
                        externalLoginInfo.ProviderDisplayName));

                if (!addLoginResult.Succeeded)
                {
                    logger.LogWarning("Failed to link Google login to existing user {Email}", email);
                    return GoogleOAuthErrorRedirect(safeReturnUrl, "account_creation_failed");
                }
            }

            if (!existingUser.EmailConfirmed)
            {
                existingUser.EmailConfirmed = true;
                await userManager.UpdateAsync(existingUser);
            }

            await signInManager.SignInAsync(existingUser, isPersistent: false);
            return Results.LocalRedirect(safeReturnUrl);
        }

        var user = new ApplicationUser
        {
            Email = email,
            EmailConfirmed = true,
            UserName = email
        };

        var createResult = await userManager.CreateAsync(user);
        if (!createResult.Succeeded)
        {
            return GoogleOAuthErrorRedirect(safeReturnUrl, "account_creation_failed");
        }

        var roleResult = await userManager.AddToRoleAsync(user, AppRoles.User);
        if (!roleResult.Succeeded)
        {
            await userManager.DeleteAsync(user);
            return GoogleOAuthErrorRedirect(safeReturnUrl, "account_creation_failed");
        }

        var loginResult = await userManager.AddLoginAsync(
            user,
            new UserLoginInfo(
                externalLoginInfo.LoginProvider,
                externalLoginInfo.ProviderKey,
                externalLoginInfo.ProviderDisplayName));
        if (!loginResult.Succeeded)
        {
            await userManager.DeleteAsync(user);
            return GoogleOAuthErrorRedirect(safeReturnUrl, "account_creation_failed");
        }

        await signInManager.SignInAsync(user, isPersistent: false);
        return Results.LocalRedirect(safeReturnUrl);
    }

    private static async Task<IResult> LoginAsync(
        LoginRequest request,
        UserManager<ApplicationUser> userManager,
        SignInManager<ApplicationUser> signInManager)
    {
        var email = request.Email?.Trim();
        var password = request.Password;

        if (string.IsNullOrWhiteSpace(email) || string.IsNullOrWhiteSpace(password))
        {
            return Results.ValidationProblem(new Dictionary<string, string[]>
            {
                [nameof(request.Email)] = ["Email is required."],
                [nameof(request.Password)] = ["Password is required."]
            });
        }

        var user = await userManager.FindByEmailAsync(email);
        if (user is null)
        {
            return InvalidCredentials();
        }

        var passwordResult = await signInManager.CheckPasswordSignInAsync(user, password, lockoutOnFailure: false);
        if (!passwordResult.Succeeded)
        {
            return InvalidCredentials();
        }

        await signInManager.SignInAsync(user, isPersistent: false);

        return Results.Ok(await BuildCurrentUserResponseAsync(userManager, user, authenticated: true));
    }

    private static async Task<IResult> MeAsync(
        HttpContext httpContext,
        UserManager<ApplicationUser> userManager)
    {
        if (httpContext.User.Identity?.IsAuthenticated != true)
        {
            return Results.Ok(new CurrentUserResponse(false, null, null, false, []));
        }

        var user = await userManager.GetUserAsync(httpContext.User);
        if (user is null)
        {
            return Results.Ok(new CurrentUserResponse(false, null, null, false, []));
        }

        return Results.Ok(await BuildCurrentUserResponseAsync(userManager, user, authenticated: true));
    }

    private static async Task<CurrentUserResponse> BuildCurrentUserResponseAsync(
        UserManager<ApplicationUser> userManager,
        ApplicationUser user,
        bool authenticated)
    {
        var roles = await userManager.GetRolesAsync(user);
        return new CurrentUserResponse(authenticated, user.Id, user.Email, user.EmailConfirmed, roles.ToArray());
    }

    private static async Task<ApplicationUser?> GetCurrentUserAsync(
        HttpContext httpContext,
        UserManager<ApplicationUser> userManager)
    {
        if (httpContext.User.Identity?.IsAuthenticated != true)
        {
            return null;
        }

        return await userManager.GetUserAsync(httpContext.User);
    }

    internal static string GetSafeReturnUrl(string? returnUrl) =>
        IsLocalReturnUrl(returnUrl) ? returnUrl! : "/chat";

    internal static bool IsLocalReturnUrl(string? returnUrl)
    {
        if (string.IsNullOrWhiteSpace(returnUrl) ||
            !returnUrl.StartsWith("/", StringComparison.Ordinal) ||
            (returnUrl.Length > 1 && (returnUrl[1] == '/' || returnUrl[1] == '\\')))
        {
            return false;
        }

        return !returnUrl.Any(char.IsControl) &&
            !returnUrl.Contains('\\') &&
            !returnUrl.Contains("://", StringComparison.Ordinal);
    }

    internal static bool IsGoogleEmailVerified(ClaimsPrincipal principal) =>
        principal.Claims
            .Where(claim => claim.Type is GoogleOAuthSettings.EmailVerifiedClaimType or "email_verified" or "verified_email")
            .Any(claim => bool.TryParse(claim.Value, out var verified) && verified);

    private static IResult GoogleOAuthDisabledResult() => Results.Problem(
        title: "Google OAuth is disabled.",
        detail: "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable Google sign-in.",
        statusCode: StatusCodes.Status503ServiceUnavailable);

    private static IResult GoogleOAuthErrorRedirect(string returnUrl, string errorCode)
    {
        var loginUrl = QueryHelpers.AddQueryString(
            "/login",
            new Dictionary<string, string?>
            {
                ["error"] = errorCode,
                ["from"] = returnUrl
            });

        return Results.LocalRedirect(loginUrl);
    }

    private static IResult InvalidCredentials() => Results.Problem(
        title: "Invalid login attempt.",
        detail: "The provided credentials are invalid.",
        statusCode: StatusCodes.Status401Unauthorized);
}

internal static class IdentityResultExtensions
{
    public static Dictionary<string, string[]> ToDictionary(this IdentityResult result)
    {
        var errors = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);

        foreach (var error in result.Errors)
        {
            var key = string.IsNullOrWhiteSpace(error.Code) ? string.Empty : error.Code;
            if (!errors.TryGetValue(key, out var messages))
            {
                messages = [];
                errors[key] = messages;
            }

            messages.Add(error.Description);
        }

        return errors.ToDictionary(pair => pair.Key, pair => pair.Value.ToArray(), StringComparer.OrdinalIgnoreCase);
    }
}
