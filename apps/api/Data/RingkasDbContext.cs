using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContext(DbContextOptions<RingkasDbContext> options) : IdentityDbContext<ApplicationUser>(options)
{
    public DbSet<Document> Documents => Set<Document>();
    public DbSet<IngestionJob> IngestionJobs => Set<IngestionJob>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<Document>(entity =>
        {
            entity.ToTable("documents", table =>
            {
                table.HasCheckConstraint("CK_documents_publication_year", "publication_year > 0");
                table.HasCheckConstraint("CK_documents_page_count", "page_count IS NULL OR page_count > 0");
                table.HasCheckConstraint(
                    "CK_documents_ingestion_status",
                    "ingestion_status IN ('pending', 'downloaded', 'parsed', 'indexed', 'failed', 'unsupported_or_extraction_failed')");
            });

            entity.HasKey(document => document.Id);
            entity.Property(document => document.Id).HasColumnName("id").HasColumnType("uuid").ValueGeneratedNever();
            entity.Property(document => document.Title).HasColumnName("title").HasMaxLength(500).IsRequired();
            entity.Property(document => document.PublicationYear).HasColumnName("publication_year").IsRequired();
            entity.Property(document => document.ReleaseDate).HasColumnName("release_date").HasColumnType("date");
            entity.Property(document => document.Region).HasColumnName("region").HasMaxLength(200).IsRequired();
            entity.Property(document => document.RegionLevel).HasColumnName("region_level").HasMaxLength(64).IsRequired();
            entity.Property(document => document.Topic).HasColumnName("topic").HasMaxLength(200);
            entity.Property(document => document.CatalogNumber).HasColumnName("catalog_number").HasMaxLength(128);
            entity.Property(document => document.PublicationNumber).HasColumnName("publication_number").HasMaxLength(128);
            entity.Property(document => document.SourcePageUrl).HasColumnName("source_page_url").HasColumnType("text").IsRequired();
            entity.Property(document => document.PdfUrl).HasColumnName("pdf_url").HasColumnType("text");
            entity.Property(document => document.LocalPdfPath).HasColumnName("local_pdf_path").HasColumnType("text");
            entity.Property(document => document.Language).HasColumnName("language").HasMaxLength(32);
            entity.Property(document => document.PageCount).HasColumnName("page_count");
            entity.Property(document => document.IngestionStatus).HasColumnName("ingestion_status").HasMaxLength(40)
                .HasDefaultValue(DocumentIngestionStatuses.Pending).IsRequired();
            entity.Property(document => document.Checksum).HasColumnName("checksum").HasColumnType("text").IsRequired();
            entity.Property(document => document.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();
            entity.Property(document => document.IngestedAt).HasColumnName("ingested_at").HasColumnType("timestamp with time zone");
            entity.Property(document => document.ErrorMessage).HasColumnName("error_message").HasMaxLength(2000);

            entity.HasIndex(document => document.PublicationYear).HasDatabaseName("IX_documents_publication_year");
            entity.HasIndex(document => document.Region).HasDatabaseName("IX_documents_region");
            entity.HasIndex(document => document.IngestionStatus).HasDatabaseName("IX_documents_ingestion_status");
            entity.HasIndex(document => document.Checksum).HasDatabaseName("IX_documents_checksum");
        });

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
