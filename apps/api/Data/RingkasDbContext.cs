using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContext(DbContextOptions<RingkasDbContext> options) : IdentityDbContext<ApplicationUser>(options)
{
    public DbSet<IngestionJob> IngestionJobs => Set<IngestionJob>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<IngestionJob>(entity =>
        {
            entity.ToTable("ingestion_jobs", table =>
            {
                table.HasCheckConstraint(
                    "CK_ingestion_jobs_status",
                    "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')");
                table.HasCheckConstraint("CK_ingestion_jobs_year_range", "scope_year_start <= scope_year_end");
                table.HasCheckConstraint("CK_ingestion_jobs_max_documents", "max_documents > 0");
            });

            entity.HasKey(job => job.Id);
            entity.Property(job => job.Id).HasColumnName("id").ValueGeneratedNever();
            entity.Property(job => job.RequestedByUserId).HasColumnName("requested_by_user_id").IsRequired();
            entity.Property(job => job.Status).HasColumnName("status").HasMaxLength(32).HasDefaultValue(IngestionJobStatuses.Queued).IsRequired();
            entity.Property(job => job.ScopeRegion).HasColumnName("scope_region").HasMaxLength(200).IsRequired();
            entity.Property(job => job.ScopeYearStart).HasColumnName("scope_year_start").IsRequired();
            entity.Property(job => job.ScopeYearEnd).HasColumnName("scope_year_end").IsRequired();
            entity.Property(job => job.MaxDocuments).HasColumnName("max_documents").IsRequired();
            entity.Property(job => job.StartedAt).HasColumnName("started_at").HasColumnType("timestamp with time zone");
            entity.Property(job => job.CompletedAt).HasColumnName("completed_at").HasColumnType("timestamp with time zone");
            entity.Property(job => job.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone").HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();
            entity.Property(job => job.ErrorSummary).HasColumnName("error_summary");

            entity.HasOne<ApplicationUser>()
                .WithMany()
                .HasForeignKey(job => job.RequestedByUserId)
                .OnDelete(DeleteBehavior.Restrict)
                .IsRequired();

            entity.HasIndex(job => job.Status).HasDatabaseName("IX_ingestion_jobs_status");
            entity.HasIndex(job => new { job.Status, job.CreatedAt }).HasDatabaseName("IX_ingestion_jobs_status_created_at");
        });
    }
}
