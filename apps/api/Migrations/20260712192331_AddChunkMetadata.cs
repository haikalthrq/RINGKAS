using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddChunkMetadata : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "chunks",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    document_id = table.Column<Guid>(type: "uuid", nullable: false),
                    chunk_index = table.Column<int>(type: "integer", nullable: false),
                    text = table.Column<string>(type: "text", nullable: false),
                    page_start = table.Column<int>(type: "integer", nullable: true),
                    page_end = table.Column<int>(type: "integer", nullable: true),
                    section_heading = table.Column<string>(type: "text", nullable: true),
                    extraction_method = table.Column<string>(type: "text", nullable: false),
                    low_structure_confidence = table.Column<bool>(type: "boolean", nullable: false),
                    source_url = table.Column<string>(type: "text", nullable: false),
                    qdrant_point_id = table.Column<string>(type: "text", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_chunks", x => x.id);
                    table.CheckConstraint("CK_chunks_chunk_index_non_negative", "chunk_index >= 0");
                    table.CheckConstraint("CK_chunks_extraction_method", "extraction_method = 'text_layer'");
                    table.CheckConstraint("CK_chunks_page_end_positive", "page_end IS NULL OR page_end > 0");
                    table.CheckConstraint("CK_chunks_page_range_complete", "(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end IS NOT NULL)");
                    table.CheckConstraint("CK_chunks_page_range_order", "page_start IS NULL OR page_end >= page_start");
                    table.CheckConstraint("CK_chunks_page_start_positive", "page_start IS NULL OR page_start > 0");
                    table.CheckConstraint("CK_chunks_qdrant_point_id_not_blank", "qdrant_point_id ~ '[^[:space:]]'");
                    table.CheckConstraint("CK_chunks_source_url_not_blank", "source_url ~ '[^[:space:]]'");
                    table.CheckConstraint("CK_chunks_text_not_blank", "text ~ '[^[:space:]]'");
                    table.ForeignKey(
                        name: "FK_chunks_documents_document_id",
                        column: x => x.document_id,
                        principalTable: "documents",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_chunks_document_id_chunk_index",
                table: "chunks",
                columns: new[] { "document_id", "chunk_index" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_chunks_qdrant_point_id",
                table: "chunks",
                column: "qdrant_point_id",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "chunks");
        }
    }
}
