using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Npgsql;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContextFactory : IDesignTimeDbContextFactory<RingkasDbContext>
{
    public RingkasDbContext CreateDbContext(string[] args)
    {
        var connectionString = Environment.GetEnvironmentVariable("DATABASE_URL")
            ?? Environment.GetEnvironmentVariable("ConnectionStrings__DefaultConnection")
            ?? "Host=localhost;Port=5432;Database=ringkas;Username=ringkas;Password=change-me-locally";

        var options = new DbContextOptionsBuilder<RingkasDbContext>()
            .UseNpgsql(ConvertDatabaseUrl(connectionString))
            .Options;

        return new RingkasDbContext(options);
    }

    private static string ConvertDatabaseUrl(string connectionString)
    {
        if (!Uri.TryCreate(connectionString, UriKind.Absolute, out var uri) ||
            (uri.Scheme != "postgres" && uri.Scheme != "postgresql"))
        {
            return connectionString;
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
}
