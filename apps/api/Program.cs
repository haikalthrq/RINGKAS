using Microsoft.EntityFrameworkCore;
using Npgsql;
using Ringkas.Api.Data;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddDbContext<RingkasDbContext>(options =>
    options.UseNpgsql(GetPostgresConnectionString(builder.Configuration)));

var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));

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
