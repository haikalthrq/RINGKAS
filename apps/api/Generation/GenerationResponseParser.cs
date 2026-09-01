using System.Text.Json;

namespace Ringkas.Api.Generation;

internal static class GenerationResponseParser
{
    public static GenerationResult Parse(string content, GenerationProvider provider, string model)
    {
        try
        {
            using var document = JsonDocument.Parse(content);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("choices", out var choices) ||
                choices.ValueKind != JsonValueKind.Array ||
                choices.GetArrayLength() == 0)
            {
                throw Malformed();
            }

            var choice = choices[0];
            if (choice.ValueKind != JsonValueKind.Object ||
                !choice.TryGetProperty("message", out var message) ||
                message.ValueKind != JsonValueKind.Object ||
                !message.TryGetProperty("content", out var text) ||
                text.ValueKind != JsonValueKind.String ||
                string.IsNullOrWhiteSpace(text.GetString()))
            {
                throw Malformed();
            }

            return new GenerationResult(text.GetString()!, provider, model, ParseUsage(root));
        }
        catch (JsonException)
        {
            throw Malformed();
        }
    }

    public static GenerationResult ParseResponsesApi(string content, GenerationProvider provider, string model)
    {
        try
        {
            using var document = JsonDocument.Parse(content);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("output", out var output) ||
                output.ValueKind != JsonValueKind.Array)
            {
                throw Malformed();
            }

            var text = output.EnumerateArray()
                .Where(item => item.ValueKind == JsonValueKind.Object &&
                    item.TryGetProperty("type", out var type) &&
                    type.ValueKind == JsonValueKind.String &&
                    type.GetString() == "message")
                .SelectMany(item => item.TryGetProperty("content", out var contentItems) &&
                    contentItems.ValueKind == JsonValueKind.Array
                    ? contentItems.EnumerateArray()
                    : [])
                .Where(item => item.ValueKind == JsonValueKind.Object &&
                    item.TryGetProperty("type", out var type) &&
                    type.ValueKind == JsonValueKind.String &&
                    type.GetString() == "output_text")
                .Select(item => item.TryGetProperty("text", out var value) && value.ValueKind == JsonValueKind.String
                    ? value.GetString()
                    : null)
                .FirstOrDefault(value => !string.IsNullOrWhiteSpace(value));

            if (string.IsNullOrWhiteSpace(text))
            {
                throw Malformed();
            }

            return new GenerationResult(text, provider, model, ParseResponsesUsage(root));
        }
        catch (JsonException)
        {
            throw Malformed();
        }
    }

    private static GenerationUsage? ParseUsage(JsonElement root)
    {
        if (!root.TryGetProperty("usage", out var usage))
        {
            return null;
        }

        if (usage.ValueKind != JsonValueKind.Object)
        {
            throw Malformed();
        }

        return new GenerationUsage(
            ReadUsageValue(usage, "prompt_tokens"),
            ReadUsageValue(usage, "completion_tokens"),
            ReadUsageValue(usage, "total_tokens"));
    }

    private static GenerationUsage? ParseResponsesUsage(JsonElement root)
    {
        if (!root.TryGetProperty("usage", out var usage))
        {
            return null;
        }

        if (usage.ValueKind != JsonValueKind.Object)
        {
            throw Malformed();
        }

        return new GenerationUsage(
            ReadUsageValue(usage, "input_tokens"),
            ReadUsageValue(usage, "output_tokens"),
            ReadUsageValue(usage, "total_tokens"));
    }

    private static int? ReadUsageValue(JsonElement usage, string name)
    {
        if (!usage.TryGetProperty(name, out var value))
        {
            return null;
        }

        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out var result) || result < 0)
        {
            throw Malformed();
        }

        return result;
    }

    private static GenerationException Malformed() =>
        new(GenerationFailureCategory.MalformedResponse, "Generation provider returned an unusable response.");
}
