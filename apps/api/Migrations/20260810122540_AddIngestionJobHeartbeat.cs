using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Ringkas.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddIngestionJobHeartbeat : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "heartbeat_at",
                table: "ingestion_jobs",
                type: "timestamp with time zone",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "heartbeat_at",
                table: "ingestion_jobs");
        }
    }
}
