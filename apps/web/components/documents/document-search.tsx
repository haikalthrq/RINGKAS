"use client";

import { useState } from "react";
import { apiRequest } from "@/lib/api-client";

interface DocumentSearchResponse {
  page: number;
  pageSize: number;
  totalCount: number;
  items: DocumentSearchItem[];
}

interface DocumentSearchItem {
  documentId: string;
  title: string;
  publicationYear: number;
  region: string;
  regionLevel: string;
  topic: string | null;
  sourcePageUrl: string;
  pdfUrl: string | null;
}

export function DocumentSearch() {
  const [results, setResults] = useState<DocumentSearchResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const q = String(formData.get("q") ?? "").trim();
    const year = String(formData.get("year") ?? "").trim();
    const topic = String(formData.get("topic") ?? "").trim();

    if (!q && !year && !topic) {
      setError("Enter a keyword, year, or topic to search.");
      setResults(null);
      return;
    }

    const params = new URLSearchParams({ page: "1", page_size: "20" });
    if (q) params.set("q", q);
    if (year) params.set("year", year);
    if (topic) params.set("topic", topic);

    setLoading(true);
    setError("");
    setResults(null);
    try {
      setResults(await apiRequest<DocumentSearchResponse>(`/api/documents/search?${params}`));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Search is unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="feature-stack">
      <form className="search-form" onSubmit={handleSubmit}>
        <label className="field search-field" htmlFor="document-query">
          Search publications
          <input id="document-query" name="q" type="search" placeholder="Search by title or keyword" maxLength={200} />
        </label>
        <div className="filter-grid">
          <label className="field" htmlFor="document-year">Year<input id="document-year" name="year" type="number" min="1" placeholder="e.g. 2024" /></label>
          <label className="field" htmlFor="document-topic">Topic / subject<input id="document-topic" name="topic" placeholder="e.g. Population" maxLength={200} /></label>
        </div>
        <button className="primary-button" type="submit" disabled={loading}>{loading ? "Searching..." : "Search publications"}</button>
      </form>
      <section className="results-region" aria-labelledby="results-title" aria-live="polite" aria-busy={loading}>
        <div className="panel-heading">
          <h2 id="results-title">Results</h2>
          <span className="state-badge">{loading ? "Loading" : error ? "Error" : results ? `${results.totalCount} found` : "Ready"}</span>
        </div>
        {loading ? <p className="state-message" role="status">Retrieving publications...</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {!loading && !error && !results ? <p className="state-message">Enter at least one search criterion to find indexed BPS publications.</p> : null}
        {results?.items.length === 0 ? <p className="state-message">No publications matched these search criteria.</p> : null}
        {results?.items.length ? (
          <div className="document-results">
            {results.items.map((document) => <DocumentResult key={document.documentId} document={document} />)}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function DocumentResult({ document }: { document: DocumentSearchItem }) {
  const source = document.sourcePageUrl || document.pdfUrl;
  let safeSource: string | null = null;
  try {
    const url = source ? new URL(source) : null;
    if (url?.protocol === "https:" || url?.protocol === "http:") safeSource = source;
  } catch {
    // Invalid source URLs are shown as unavailable rather than rendered as links.
  }

  return (
    <article className="document-card">
      <h3>{document.title}</h3>
      <dl className="metadata-list">
        <div><dt>Year</dt><dd>{document.publicationYear}</dd></div>
        <div><dt>Region</dt><dd>{document.region}</dd></div>
        <div><dt>Region level</dt><dd>{document.regionLevel}</dd></div>
        {document.topic ? <div><dt>Topic</dt><dd>{document.topic}</dd></div> : null}
      </dl>
      {safeSource
        ? <a className="source-link" href={safeSource} target="_blank" rel="noreferrer">View source publication</a>
        : <p className="source-placeholder">Source link unavailable.</p>}
    </article>
  );
}
