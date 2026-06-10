using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using Ringkas.Api.Auth;
using Ringkas.Api.Data;
using Ringkas.Api.Endpoints;
using Ringkas.Api.Middleware;
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

builder.Services.AddAuthorization();
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    options.AddPolicy(RateLimitPolicies.Auth, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: GetRateLimitPartitionKey(httpContext, RateLimitPolicies.Auth),
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 5,
                Window = TimeSpan.FromMinutes(1),
                QueueLimit = 0,
                AutoReplenishment = true
            }));

    options.AddPolicy(RateLimitPolicies.Chat, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: GetRateLimitPartitionKey(httpContext, RateLimitPolicies.Chat),
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 10,
                Window = TimeSpan.FromMinutes(1),
                QueueLimit = 0,
                AutoReplenishment = true
            }));

    options.AddPolicy(RateLimitPolicies.AdminIngestion, httpContext =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: GetRateLimitPartitionKey(httpContext, RateLimitPolicies.AdminIngestion),
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 3,
                Window = TimeSpan.FromMinutes(1),
                QueueLimit = 0,
                AutoReplenishment = true
            }));
});
builder.Services.AddScoped<IdentityRoleSeeder>();
builder.Services.AddSingleton(GoogleOAuthSettings.FromConfiguration(builder.Configuration));

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
