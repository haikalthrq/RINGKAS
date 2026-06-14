"use client";

import { useState } from "react";

export function DocumentSearch() {
  const [searched, setSearched] = useState(false);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearched(true);
  }

  return (
    <div className="feature-stack">
      <form className="search-form" onSubmit={handleSubmit}>
        <label className="field search-field" htmlFor="document-query">
          Search publications
          <input id="document-query" name="query" type="search" placeholder="Search by title or keyword" />
        </label>
        <div className="filter-grid">
          <label className="field" htmlFor="document-year">Year<input id="document-year" name="year" inputMode="numeric" placeholder="e.g. 2024" /></label>
          <label className="field" htmlFor="document-region">Region<input id="document-region" name="region" placeholder="e.g. Jawa Barat" /></label>
          <label className="field" htmlFor="document-topic">Topic / subject<input id="document-topic" name="topic" placeholder="e.g. Population" /></label>
        </div>
        <button className="primary-button" type="submit">Search publications</button>
      </form>
      {searched ? <p className="form-note" role="status">Search preview only. No request was sent.</p> : null}
      <section className="results-region" aria-labelledby="results-title" aria-live="polite">
        <div className="panel-heading"><h2 id="results-title">Results</h2><span className="state-badge">Empty</span></div>
        <article className="document-card">
          <div><p className="preview-label">Preview card</p><h3>Publication title placeholder</h3></div>
          <dl className="metadata-list"><div><dt>Year</dt><dd>Year placeholder</dd></div><div><dt>Region</dt><dd>Region placeholder</dd></div><div><dt>Topic</dt><dd>Topic placeholder</dd></div></dl>
          <p className="source-placeholder">Source URL will appear here after search integration.</p>
        </article>
        <p className="state-message">No real documents are shown in this skeleton.</p>
      </section>
      <div className="state-preview" aria-label="Search state previews">
        <span>Loading: retrieving results</span><span>Error: search unavailable</span>
      </div>
      <p className="limitation-note" role="note"><strong>Search state:</strong> Loading and error states will be represented here when the document search service is connected.</p>
    </div>
  );
}
