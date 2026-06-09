using Microsoft.AspNetCore.Identity;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;

namespace Ringkas.Api.Endpoints;

public static class AuthEndpoints
{
    public static IEndpointRouteBuilder MapAuthEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/auth");

        group.MapPost("/register", RegisterAsync).AllowAnonymous();
        group.MapPost("/login", LoginAsync).AllowAnonymous();
        group.MapGet("/me", MeAsync).AllowAnonymous();
        group.MapPost("/email-verification/request", RequestEmailVerificationAsync).AllowAnonymous();
        group.MapPost("/email-verification/confirm", ConfirmEmailVerificationAsync).AllowAnonymous();

        return endpoints;
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
            return Results.Problem(
                title: "Registration failed.",
                detail: string.Join(", ", roleResult.Errors.Select(error => error.Description)),
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
