using System.Diagnostics;
using Microsoft.Extensions.Primitives;

namespace Ringkas.Api.Middleware;

public sealed class RequestLoggingMiddleware(RequestDelegate next, ILogger<RequestLoggingMiddleware> logger)
{
    private const string CorrelationIdHeader = "X-Correlation-ID";
    private const string RequestIdHeader = "X-Request-ID";

    public async Task InvokeAsync(HttpContext context)
    {
        var correlationId = ResolveCorrelationId(context);
        context.Response.OnStarting(() =>
        {
            context.Response.Headers[CorrelationIdHeader] = correlationId;
            return Task.CompletedTask;
        });

        using var scope = logger.BeginScope(new Dictionary<string, object?>
        {
            ["CorrelationId"] = correlationId,
            ["RequestMethod"] = context.Request.Method,
            ["RequestPath"] = context.Request.Path.Value
        });

        var startTimestamp = Stopwatch.GetTimestamp();
        logger.LogInformation("HTTP request started");

        try
        {
            await next(context);
        }
        catch (Exception exception)
        {
            logger.LogError(exception, "HTTP request failed");

            if (!context.Response.HasStarted)
            {
                context.Response.StatusCode = StatusCodes.Status500InternalServerError;
                context.Response.ContentType = "application/json";
                await context.Response.WriteAsJsonAsync(new
                {
                    title = "An unexpected error occurred.",
                    status = StatusCodes.Status500InternalServerError,
                    correlationId
                });
                return;
            }

            throw;
        }

        var elapsed = Stopwatch.GetElapsedTime(startTimestamp);
        logger.LogInformation(
            "HTTP request completed with status {StatusCode} in {ElapsedMilliseconds} ms",
            context.Response.StatusCode,
            elapsed.TotalMilliseconds);
    }

    private static string ResolveCorrelationId(HttpContext context)
    {
        if (context.Request.Headers.TryGetValue(CorrelationIdHeader, out var correlationId) &&
            !StringValues.IsNullOrEmpty(correlationId))
        {
            return correlationId.ToString();
        }

        if (context.Request.Headers.TryGetValue(RequestIdHeader, out var requestId) &&
            !StringValues.IsNullOrEmpty(requestId))
        {
            return requestId.ToString();
        }

        return context.TraceIdentifier;
    }
}
