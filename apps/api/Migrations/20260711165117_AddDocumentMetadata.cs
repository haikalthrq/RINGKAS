using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddDocumentMetadata : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "documents",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    title = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    publication_year = table.Column<int>(type: "integer", nullable: false),
                    release_date = table.Column<DateOnly>(type: "date", nullable: true),
                    region = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    region_level = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    topic = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true),
                    catalog_number = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    publication_number = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    source_page_url = table.Column<string>(type: "text", nullable: false),
                    pdf_url = table.Column<string>(type: "text", nullable: true),
                    local_pdf_path = table.Column<string>(type: "text", nullable: true),
                    language = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    page_count = table.Column<int>(type: "integer", nullable: true),
                    ingestion_status = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false, defaultValue: "pending"),
                    checksum = table.Column<string>(type: "text", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    ingested_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    error_message = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_documents", x => x.id);
                    table.CheckConstraint("CK_documents_ingestion_status", "ingestion_status IN ('pending', 'downloaded', 'parsed', 'indexed', 'failed', 'unsupported_or_extraction_failed')");
                    table.CheckConstraint("CK_documents_page_count", "page_count IS NULL OR page_count > 0");
                    table.CheckConstraint("CK_documents_publication_year", "publication_year > 0");
                });

            migrationBuilder.CreateIndex(
                name: "IX_documents_checksum",
                table: "documents",
                column: "checksum");

            migrationBuilder.CreateIndex(
                name: "IX_documents_ingestion_status",
                table: "documents",
                column: "ingestion_status");

            migrationBuilder.CreateIndex(
                name: "IX_documents_publication_year",
                table: "documents",
                column: "publication_year");

            migrationBuilder.CreateIndex(
                name: "IX_documents_region",
                table: "documents",
                column: "region");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "documents");
        }
    }
}
