using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Ringkas.Api.Data;

#nullable disable

namespace Ringkas.Api.Migrations;

[DbContext(typeof(RingkasDbContext))]
[Migration("20260709000000_InitialCreate")]
public partial class InitialCreate : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
    }

    protected override void Down(MigrationBuilder migrationBuilder)
    {
    }
}
