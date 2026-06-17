using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddIngestionJobs : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ingestion_jobs",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    requested_by_user_id = table.Column<string>(type: "text", nullable: false),
                    status = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false, defaultValue: "queued"),
                    scope_region = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    scope_year_start = table.Column<int>(type: "integer", nullable: false),
                    scope_year_end = table.Column<int>(type: "integer", nullable: false),
                    max_documents = table.Column<int>(type: "integer", nullable: false),
                    started_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    completed_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    error_summary = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ingestion_jobs", x => x.id);
                    table.CheckConstraint("CK_ingestion_jobs_max_documents", "max_documents > 0");
                    table.CheckConstraint("CK_ingestion_jobs_status", "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')");
                    table.CheckConstraint("CK_ingestion_jobs_year_range", "scope_year_start <= scope_year_end");
                    table.ForeignKey(
                        name: "FK_ingestion_jobs_AspNetUsers_requested_by_user_id",
                        column: x => x.requested_by_user_id,
                        principalTable: "AspNetUsers",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ingestion_jobs_requested_by_user_id",
                table: "ingestion_jobs",
                column: "requested_by_user_id");

            migrationBuilder.CreateIndex(
                name: "IX_ingestion_jobs_status",
                table: "ingestion_jobs",
                column: "status");

            migrationBuilder.CreateIndex(
                name: "IX_ingestion_jobs_status_created_at",
                table: "ingestion_jobs",
                columns: new[] { "status", "created_at" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ingestion_jobs");
        }
    }
}
