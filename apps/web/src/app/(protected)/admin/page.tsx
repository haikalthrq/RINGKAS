"use client";

import { useState } from "react";
import { AdminRoleGuard } from "@/components/protected-guard";
import { apiRequest } from "@/lib/api-client";

interface IngestionJob {
  jobId: string;
  status: string;
  region: string;
  yearStart: number;
  yearEnd: number;
  maxDocuments: number;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  errorSummary: string | null;
  recentLogs: IngestionLog[];
}

interface IngestionLog {
  level: string;
  message: string;
  createdAt: string;
}

type CreatedIngestionJob = Omit<IngestionJob, "startedAt" | "completedAt" | "errorSummary" | "recentLogs">;

export default function AdminPage() {
  const [job, setJob] = useState<IngestionJob | null>(null);
  const [error, setError] = useState("");
  const [action, setAction] = useState<"trigger" | "refresh" | null>(null);

  async function triggerJob(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setAction("trigger");
    setError("");
    try {
      const created = await apiRequest<CreatedIngestionJob>("/api/admin/ingestion/jobs", {
        method: "POST",
        body: {
          region: "DKI Jakarta",
          year_start: Number(formData.get("year_start")),
          year_end: Number(formData.get("year_end")),
          max_documents: Number(formData.get("max_documents")),
          force_reprocess: false
        }
      });
      setJob({ ...created, startedAt: null, completedAt: null, errorSummary: null, recentLogs: [] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not trigger ingestion. Please try again.");
    } finally {
      setAction(null);
    }
  }

  async function refreshJob() {
    if (!job) return;
    setAction("refresh");
    setError("");
    try {
      setJob(await apiRequest<IngestionJob>(`/api/admin/ingestion/jobs/${job.jobId}`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not refresh the job. Please try again.");
    } finally {
      setAction(null);
    }
  }

  const loading = action !== null;

  return (
    <AdminRoleGuard>
      <section className="page-card admin-page" aria-labelledby="admin-title">
        <p className="eyebrow">Admin</p>
        <h1 id="admin-title">Ingestion operations</h1>
        <p className="page-intro">Trigger an ingestion run for the approved DKI Jakarta corpus, then review its status and short logs.</p>
        <div className="admin-grid">
          <section className="panel" aria-labelledby="trigger-title">
            <div className="panel-heading"><h2 id="trigger-title">Ingestion trigger</h2><span className="state-badge">DKI Jakarta</span></div>
            <form className="search-form" onSubmit={triggerJob}>
              <label className="field" htmlFor="ingestion-region">Region<input id="ingestion-region" value="DKI Jakarta" readOnly /></label>
              <div className="filter-grid">
                <label className="field" htmlFor="year-start">Year start<input id="year-start" name="year_start" type="number" min="1" defaultValue="2022" required /></label>
                <label className="field" htmlFor="year-end">Year end<input id="year-end" name="year_end" type="number" min="1" defaultValue="2026" required /></label>
                <label className="field" htmlFor="max-documents">Maximum documents<input id="max-documents" name="max_documents" type="number" min="1" max="300" defaultValue="300" required /></label>
              </div>
              <button className="primary-button" type="submit" disabled={loading}>{action === "trigger" ? "Triggering..." : "Trigger ingestion"}</button>
            </form>
          </section>
          <section className="panel" aria-labelledby="job-title" aria-live="polite" aria-busy={loading}>
            <div className="panel-heading"><h2 id="job-title">Job status</h2><span className="state-badge">{loading ? "Loading" : error ? "Error" : job?.status ?? "Empty"}</span></div>
            {action === "trigger" ? <p className="state-message" role="status">Creating the ingestion job...</p> : null}
            {action === "refresh" ? <p className="state-message" role="status">Refreshing the job status...</p> : null}
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            {!job && !loading && !error ? <p className="state-message">No ingestion job has been triggered in this session.</p> : null}
            {job ? (
              <div className="feature-stack">
                <dl className="metadata-list">
                  <div><dt>Status</dt><dd>{job.status}</dd></div>
                  <div><dt>Region</dt><dd>{job.region}</dd></div>
                  <div><dt>Year range</dt><dd>{job.yearStart}-{job.yearEnd}</dd></div>
                  <div><dt>Maximum documents</dt><dd>{job.maxDocuments}</dd></div>
                  <div><dt>Created</dt><dd><JobTime value={job.createdAt} /></dd></div>
                  <div><dt>Started</dt><dd><JobTime value={job.startedAt} /></dd></div>
                  <div><dt>Completed</dt><dd><JobTime value={job.completedAt} /></dd></div>
                  <div><dt>Job ID</dt><dd>{job.jobId}</dd></div>
                </dl>
                {job.errorSummary ? <p className="form-error"><strong>Error summary:</strong> {job.errorSummary}</p> : null}
                <button className="primary-button" type="button" onClick={refreshJob} disabled={loading}>{action === "refresh" ? "Refreshing..." : "Refresh status"}</button>
              </div>
            ) : null}
          </section>
          <section className="panel" aria-labelledby="log-title" aria-live="polite">
            <div className="panel-heading"><h2 id="log-title">Short log</h2><span className="state-badge">{job ? `${Math.min(job.recentLogs.length, 20)} entries` : "Empty"}</span></div>
            {!job ? <p>No ingestion job is available yet.</p> : null}
            {job && job.recentLogs.length === 0 ? <p>No recent log entries are available. Refresh the status to check again.</p> : null}
            {job?.recentLogs.length ? (
              <div className="document-results">
                {job.recentLogs.slice(0, 20).map((log, index) => (
                  <article className="document-card" key={`${log.createdAt}-${index}`}>
                    <div className="panel-heading"><h3>{log.level}</h3><JobTime value={log.createdAt} /></div>
                    <p>{log.message}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        </div>
      </section>
    </AdminRoleGuard>
  );
}

function JobTime({ value }: { value: string | null }) {
  if (!value) return <>Not available</>;
  return <time dateTime={value}>{new Date(value).toLocaleString()}</time>;
}
