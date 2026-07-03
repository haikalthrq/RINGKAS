using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContext(DbContextOptions<RingkasDbContext> options) : IdentityDbContext<ApplicationUser>(options)
{
    public DbSet<Document> Documents => Set<Document>();
    public DbSet<Chunk> Chunks => Set<Chunk>();
    public DbSet<IngestionJob> IngestionJobs => Set<IngestionJob>();
    public DbSet<IngestionLog> IngestionLogs => Set<IngestionLog>();
    public DbSet<ChatSession> ChatSessions => Set<ChatSession>();
    public DbSet<ChatMessage> ChatMessages => Set<ChatMessage>();

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

        modelBuilder.Entity<Chunk>(entity =>
        {
            entity.ToTable("chunks", table =>
            {
                table.HasCheckConstraint("CK_chunks_chunk_index_non_negative", "chunk_index >= 0");
                table.HasCheckConstraint("CK_chunks_page_start_positive", "page_start IS NULL OR page_start > 0");
                table.HasCheckConstraint("CK_chunks_page_end_positive", "page_end IS NULL OR page_end > 0");
                table.HasCheckConstraint(
                    "CK_chunks_page_range_complete",
                    "(page_start IS NULL AND page_end IS NULL) OR (page_start IS NOT NULL AND page_end IS NOT NULL)");
                table.HasCheckConstraint("CK_chunks_page_range_order", "page_start IS NULL OR page_end >= page_start");
                table.HasCheckConstraint("CK_chunks_extraction_method", "extraction_method = 'text_layer'");
                table.HasCheckConstraint("CK_chunks_text_not_blank", "text ~ '[^[:space:]]'");
                table.HasCheckConstraint("CK_chunks_source_url_not_blank", "source_url ~ '[^[:space:]]'");
                table.HasCheckConstraint("CK_chunks_qdrant_point_id_not_blank", "qdrant_point_id ~ '[^[:space:]]'");
            });

            entity.HasKey(chunk => chunk.Id);
            entity.Property(chunk => chunk.Id).HasColumnName("id").HasColumnType("uuid").ValueGeneratedNever();
            entity.Property(chunk => chunk.DocumentId).HasColumnName("document_id").HasColumnType("uuid").IsRequired();
            entity.Property(chunk => chunk.ChunkIndex).HasColumnName("chunk_index").IsRequired();
            entity.Property(chunk => chunk.Text).HasColumnName("text").HasColumnType("text").IsRequired();
            entity.Property(chunk => chunk.PageStart).HasColumnName("page_start");
            entity.Property(chunk => chunk.PageEnd).HasColumnName("page_end");
            entity.Property(chunk => chunk.SectionHeading).HasColumnName("section_heading").HasColumnType("text");
            entity.Property(chunk => chunk.ExtractionMethod).HasColumnName("extraction_method").HasColumnType("text").IsRequired();
            entity.Property(chunk => chunk.LowStructureConfidence).HasColumnName("low_structure_confidence").IsRequired();
            entity.Property(chunk => chunk.SourceUrl).HasColumnName("source_url").HasColumnType("text").IsRequired();
            entity.Property(chunk => chunk.QdrantPointId).HasColumnName("qdrant_point_id").HasColumnType("text").IsRequired();
            entity.Property(chunk => chunk.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();

            entity.HasOne<Document>()
                .WithMany()
                .HasForeignKey(chunk => chunk.DocumentId)
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            entity.HasIndex(chunk => new { chunk.DocumentId, chunk.ChunkIndex })
                .IsUnique()
                .HasDatabaseName("IX_chunks_document_id_chunk_index");
            entity.HasIndex(chunk => chunk.QdrantPointId)
                .IsUnique()
                .HasDatabaseName("IX_chunks_qdrant_point_id");
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

        modelBuilder.Entity<IngestionLog>(entity =>
        {
            entity.ToTable("ingestion_logs", table =>
            {
                table.HasCheckConstraint(
                    "CK_ingestion_logs_level",
                    "level IN ('info', 'warn', 'error')");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_message_not_blank",
                    "message ~ '[^[:space:]]'");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_message_length",
                    "char_length(message) <= 2000");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_metadata_object",
                    "metadata_json IS NULL OR jsonb_typeof(metadata_json) = 'object'");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_metadata_keys",
                    "metadata_json IS NULL OR jsonb_typeof(metadata_json) <> 'object' OR metadata_json - 'step_name' - 'retry_count' = '{}'::jsonb");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_step_name",
                    "metadata_json IS NULL OR NOT (metadata_json ? 'step_name') OR (jsonb_typeof(metadata_json->'step_name') = 'string' AND btrim(metadata_json->>'step_name') <> '' AND char_length(metadata_json->>'step_name') <= 128)");
                table.HasCheckConstraint(
                    "CK_ingestion_logs_retry_count",
                    "metadata_json IS NULL OR NOT (metadata_json ? 'retry_count') OR (jsonb_typeof(metadata_json->'retry_count') = 'number' AND (metadata_json->>'retry_count') ~ '^[0-9]+$')");
            });

            entity.HasKey(log => log.Id);
            entity.Property(log => log.Id).HasColumnName("id").HasColumnType("uuid").ValueGeneratedNever();
            entity.Property(log => log.JobId).HasColumnName("job_id").HasColumnType("uuid").IsRequired();
            entity.Property(log => log.DocumentId).HasColumnName("document_id").HasColumnType("uuid");
            entity.Property(log => log.Level).HasColumnName("level").HasColumnType("text").IsRequired();
            entity.Property(log => log.Message).HasColumnName("message").HasColumnType("text").IsRequired();
            entity.Property(log => log.MetadataJson).HasColumnName("metadata_json").HasColumnType("jsonb");
            entity.Property(log => log.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();

            entity.HasOne<IngestionJob>()
                .WithMany()
                .HasForeignKey(log => log.JobId)
                .HasConstraintName("FK_ingestion_logs_ingestion_jobs_job_id")
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            entity.HasOne<Document>()
                .WithMany()
                .HasForeignKey(log => log.DocumentId)
                .HasConstraintName("FK_ingestion_logs_documents_document_id")
                .OnDelete(DeleteBehavior.SetNull);

            entity.HasIndex(log => new { log.JobId, log.CreatedAt })
                .HasDatabaseName("IX_ingestion_logs_job_id_created_at");
            entity.HasIndex(log => log.DocumentId).HasDatabaseName("IX_ingestion_logs_document_id");
        });

        modelBuilder.Entity<ChatSession>(entity =>
        {
            entity.ToTable("chat_sessions", table =>
            {
                table.HasCheckConstraint(
                    "CK_chat_sessions_title",
                    "title IS NULL OR (title ~ '[^[:space:]]' AND char_length(title) <= 500)");
            });

            entity.HasKey(session => session.Id);
            entity.Property(session => session.Id).HasColumnName("id").HasColumnType("uuid").ValueGeneratedNever();
            entity.Property(session => session.UserId).HasColumnName("user_id").IsRequired();
            entity.Property(session => session.Title).HasColumnName("title").HasColumnType("text");
            entity.Property(session => session.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();
            entity.Property(session => session.UpdatedAt).HasColumnName("updated_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();

            entity.HasOne<ApplicationUser>()
                .WithMany()
                .HasForeignKey(session => session.UserId)
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            entity.HasIndex(session => new { session.UserId, session.UpdatedAt, session.Id })
                .HasDatabaseName("IX_chat_sessions_user_id_updated_at_id");
        });

        modelBuilder.Entity<ChatMessage>(entity =>
        {
            entity.ToTable("chat_messages", table =>
            {
                table.HasCheckConstraint("CK_chat_messages_role", "role IN ('user', 'assistant', 'system')");
                table.HasCheckConstraint(
                    "CK_chat_messages_content",
                    "content ~ '[^[:space:]]' AND char_length(content) <= 20000");
                table.HasCheckConstraint(
                    "CK_chat_messages_citations_array",
                    "citations_json IS NULL OR jsonb_typeof(citations_json) = 'array'");
                table.HasCheckConstraint(
                    "CK_chat_messages_provider",
                    "provider IS NULL OR provider IN ('nvidia_nim', 'cloudflare_workers_ai')");
            });

            entity.HasKey(message => message.Id);
            entity.Property(message => message.Id).HasColumnName("id").HasColumnType("uuid").ValueGeneratedNever();
            entity.Property(message => message.SessionId).HasColumnName("session_id").HasColumnType("uuid").IsRequired();
            entity.Property(message => message.Role).HasColumnName("role").HasColumnType("text").IsRequired();
            entity.Property(message => message.Content).HasColumnName("content").HasColumnType("text").IsRequired();
            entity.Property(message => message.CitationsJson).HasColumnName("citations_json").HasColumnType("jsonb");
            entity.Property(message => message.Provider).HasColumnName("provider").HasColumnType("text");
            entity.Property(message => message.CreatedAt).HasColumnName("created_at").HasColumnType("timestamp with time zone")
                .HasDefaultValueSql("CURRENT_TIMESTAMP").IsRequired();

            entity.HasOne<ChatSession>()
                .WithMany()
                .HasForeignKey(message => message.SessionId)
                .OnDelete(DeleteBehavior.Cascade)
                .IsRequired();

            entity.HasIndex(message => new { message.SessionId, message.CreatedAt, message.Id })
                .HasDatabaseName("IX_chat_messages_session_id_created_at_id");
        });
    }
}
