using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using System.Globalization;
using Npgsql;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;
using Ringkas.Api.Endpoints;
using Ringkas.Api.Middleware;
using Ringkas.Api.Generation;
using System.Security.Claims;
using System.Threading.RateLimiting;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddDbContext<RingkasDbContext>(options =>
    options.UseNpgsql(GetPostgresConnectionString(builder.Configuration)));

builder.Services
    .AddIdentity<ApplicationUser, Microsoft.AspNetCore.Identity.IdentityRole>(options =>
    {
        options.User.RequireUniqueEmail = true;
        options.SignIn.RequireConfirmedAccount = false;
    })
    .AddEntityFrameworkStores<RingkasDbContext>();

builder.Services.ConfigureApplicationCookie(options =>
{
    options.Cookie.HttpOnly = true;
    options.Cookie.SameSite = SameSiteMode.Lax;
    options.Cookie.SecurePolicy = CookieSecurePolicy.SameAsRequest;
    options.SlidingExpiration = true;
    options.ExpireTimeSpan = TimeSpan.FromDays(7);
    options.Events.OnRedirectToLogin = context =>
    {
        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
        return Task.CompletedTask;
    };
    options.Events.OnRedirectToAccessDenied = context =>
    {
        context.Response.StatusCode = StatusCodes.Status403Forbidden;
        return Task.CompletedTask;
    };
});

builder.Services.AddAuthorization(options =>
{
    options.AddPolicy(AuthorizationPolicies.RegisteredUser, policy =>
        policy.RequireRole(AppRoles.User, AppRoles.Admin, AppRoles.SystemMaintainer));
});
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    ConfigureFixedWindowPolicy(options, builder.Configuration, RateLimitPolicies.Auth, "RateLimits:Auth", 5, 60);
    ConfigureFixedWindowPolicy(options, builder.Configuration, RateLimitPolicies.Chat, "RateLimits:Chat", 10, 60);
    ConfigureFixedWindowPolicy(options, builder.Configuration, RateLimitPolicies.AdminIngestion, "RateLimits:AdminIngestion", 3, 60);
});
builder.Services.AddScoped<IdentityRoleSeeder>();
builder.Services.AddSingleton(GoogleOAuthSettings.FromConfiguration(builder.Configuration));
builder.Services.AddGenerationClients();

var app = builder.Build();

app.UseMiddleware<RequestLoggingMiddleware>();
app.UseAuthentication();
app.UseRateLimiter();
app.UseAuthorization();

using (var scope = app.Services.CreateScope())
{
    var seeder = scope.ServiceProvider.GetRequiredService<IdentityRoleSeeder>();
    await seeder.SeedAsync();
}

app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));
app.MapAuthEndpoints();
app.MapDocumentEndpoints();
app.MapSourceEndpoints();

app.Run();

static string GetPostgresConnectionString(IConfiguration configuration)
{
    var databaseUrl = configuration["DATABASE_URL"];
    if (!string.IsNullOrWhiteSpace(databaseUrl))
    {
        return ConvertDatabaseUrl(databaseUrl);
    }

    var defaultConnection = configuration.GetConnectionString("DefaultConnection");
    if (!string.IsNullOrWhiteSpace(defaultConnection))
    {
        return defaultConnection;
    }

    throw new InvalidOperationException(
        "PostgreSQL connection string is not configured. Set DATABASE_URL or ConnectionStrings:DefaultConnection.");
}

static string ConvertDatabaseUrl(string databaseUrl)
{
    if (!Uri.TryCreate(databaseUrl, UriKind.Absolute, out var uri) ||
        (uri.Scheme != "postgres" && uri.Scheme != "postgresql"))
    {
        return databaseUrl;
    }

    var userInfo = uri.UserInfo.Split(':', 2);
    var builder = new NpgsqlConnectionStringBuilder
    {
        Host = uri.Host,
        Port = uri.Port > 0 ? uri.Port : 5432,
        Database = uri.AbsolutePath.TrimStart('/'),
        Username = Uri.UnescapeDataString(userInfo.ElementAtOrDefault(0) ?? string.Empty),
        Password = Uri.UnescapeDataString(userInfo.ElementAtOrDefault(1) ?? string.Empty)
    };

    foreach (var pair in uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
    {
        var parts = pair.Split('=', 2);
        var key = Uri.UnescapeDataString(parts[0]);
        var value = Uri.UnescapeDataString(parts.ElementAtOrDefault(1) ?? string.Empty);

        builder[key] = value;
    }

    return builder.ConnectionString;
}

static string GetRateLimitPartitionKey(HttpContext httpContext, string scope)
{
    var userId = httpContext.User.FindFirstValue(ClaimTypes.NameIdentifier);
    var clientAddress = httpContext.Connection.RemoteIpAddress?.ToString();
    var identifier = !string.IsNullOrWhiteSpace(userId)
        ? $"user:{userId}"
        : !string.IsNullOrWhiteSpace(clientAddress)
            ? $"ip:{clientAddress}"
            : $"trace:{httpContext.TraceIdentifier}";

    return $"{scope}:{identifier}";
}

static void ConfigureFixedWindowPolicy(
    RateLimiterOptions options,
    IConfiguration configuration,
    string policyName,
    string sectionPath,
    int defaultPermitLimit,
    int defaultWindowSeconds)
{
    var section = configuration.GetSection(sectionPath);
    var permitLimit = ReadPositiveInt(section["PermitLimit"], defaultPermitLimit);
    var windowSeconds = ReadPositiveInt(section["WindowSeconds"], defaultWindowSeconds);

    options.AddPolicy(policyName, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: GetRateLimitPartitionKey(httpContext, policyName),
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = permitLimit,
                Window = TimeSpan.FromSeconds(windowSeconds),
                QueueLimit = 0,
                AutoReplenishment = true
            }));
}

static int ReadPositiveInt(string? value, int fallback)
{
    return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed) && parsed > 0
        ? parsed
        : fallback;
}
