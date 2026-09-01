using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations;

public partial class AddOpenCodeZenProvider : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropCheckConstraint(
            name: "CK_chat_messages_provider",
            table: "chat_messages");

        migrationBuilder.AddCheckConstraint(
            name: "CK_chat_messages_provider",
            table: "chat_messages",
            sql: "provider IS NULL OR provider IN ('nvidia_nim', 'cloudflare_workers_ai', 'opencode_zen')");
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.DropCheckConstraint(
            name: "CK_chat_messages_provider",
            table: "chat_messages");

        migrationBuilder.AddCheckConstraint(
            name: "CK_chat_messages_provider",
            table: "chat_messages",
            sql: "provider IS NULL OR provider IN ('nvidia_nim', 'cloudflare_workers_ai')");
    }
}
