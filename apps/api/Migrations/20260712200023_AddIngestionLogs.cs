using System;
using System.Text.Json;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddIngestionLogs : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ingestion_logs",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    job_id = table.Column<Guid>(type: "uuid", nullable: false),
                    document_id = table.Column<Guid>(type: "uuid", nullable: true),
                    level = table.Column<string>(type: "text", nullable: false),
                    message = table.Column<string>(type: "text", nullable: false),
                    metadata_json = table.Column<JsonDocument>(type: "jsonb", nullable: true),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ingestion_logs", x => x.id);
                    table.CheckConstraint("CK_ingestion_logs_level", "level IN ('info', 'warn', 'error')");
                    table.CheckConstraint("CK_ingestion_logs_message_length", "char_length(message) <= 2000");
                    table.CheckConstraint("CK_ingestion_logs_message_not_blank", "message ~ '[^[:space:]]'");
                    table.CheckConstraint("CK_ingestion_logs_metadata_keys", "metadata_json IS NULL OR jsonb_typeof(metadata_json) <> 'object' OR metadata_json - 'step_name' - 'retry_count' = '{}'::jsonb");
                    table.CheckConstraint("CK_ingestion_logs_metadata_object", "metadata_json IS NULL OR jsonb_typeof(metadata_json) = 'object'");
                    table.CheckConstraint("CK_ingestion_logs_retry_count", "metadata_json IS NULL OR NOT (metadata_json ? 'retry_count') OR (jsonb_typeof(metadata_json->'retry_count') = 'number' AND (metadata_json->>'retry_count') ~ '^[0-9]+$')");
                    table.CheckConstraint("CK_ingestion_logs_step_name", "metadata_json IS NULL OR NOT (metadata_json ? 'step_name') OR (jsonb_typeof(metadata_json->'step_name') = 'string' AND btrim(metadata_json->>'step_name') <> '' AND char_length(metadata_json->>'step_name') <= 128)");
                    table.ForeignKey(
                        name: "FK_ingestion_logs_documents_document_id",
                        column: x => x.document_id,
                        principalTable: "documents",
                        principalColumn: "id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_ingestion_logs_ingestion_jobs_job_id",
                        column: x => x.job_id,
                        principalTable: "ingestion_jobs",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ingestion_logs_document_id",
                table: "ingestion_logs",
                column: "document_id");

            migrationBuilder.CreateIndex(
                name: "IX_ingestion_logs_job_id_created_at",
                table: "ingestion_logs",
                columns: new[] { "job_id", "created_at" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ingestion_logs");
        }
    }
}
