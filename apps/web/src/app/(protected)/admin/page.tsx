import { AdminRoleGuard } from "@/components/protected-guard";

export default function AdminPage() {
  return (
    <AdminRoleGuard>
      <section className="page-card admin-page" aria-labelledby="admin-title">
        <p className="eyebrow">Admin</p>
        <h1 id="admin-title">Ingestion operations</h1>
        <p className="page-intro">Trigger an ingestion run and review its status and short logs. Controls remain disconnected until backend integration.</p>
        <div className="admin-grid">
          <section className="panel" aria-labelledby="trigger-title">
            <div className="panel-heading"><h2 id="trigger-title">Ingestion trigger</h2><span className="state-badge">Placeholder</span></div>
            <p>Start a corpus ingestion run from the approved source.</p>
            <button className="primary-button" type="button" disabled>Trigger ingestion</button>
            <p className="panel-note">Backend integration is not implemented yet.</p>
          </section>
          <section className="panel" aria-labelledby="job-title" aria-live="polite">
            <div className="panel-heading"><h2 id="job-title">Job status</h2><span className="state-badge">Empty</span></div>
            <p>No ingestion job is being tracked in this preview.</p>
            <div className="state-preview" aria-label="Job status state previews"><span>Pending</span><span>Success</span><span>Error</span></div>
          </section>
          <section className="panel" aria-labelledby="log-title">
            <div className="panel-heading"><h2 id="log-title">Short log</h2><span className="state-badge">Empty</span></div>
            <p>No ingestion log is available yet.</p>
          </section>
        </div>
      </section>
    </AdminRoleGuard>
  );
}
