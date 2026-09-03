"use client";

import { useState } from "react";
import { apiRequest } from "@/lib/api-client";
import { useInterfaceLanguage } from "@/lib/language";

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
  const [language] = useInterfaceLanguage();
  const isEn = language === "en";

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const q = String(formData.get("q") ?? "").trim();
    const year = String(formData.get("year") ?? "").trim();
    const topic = String(formData.get("topic") ?? "").trim();

    if (!q && !year && !topic) {
      setError(isEn ? "Enter a keyword, year, or topic to search." : "Masukkan kata kunci, tahun, atau topik pencarian.");
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
      setError(requestError instanceof Error ? requestError.message : (isEn ? "Search is unavailable. Please try again." : "Layanan pencarian belum dapat dihubungi. Silakan coba lagi."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="feature-stack">
      <form className="search-form" onSubmit={handleSubmit}>
        <label className="field search-field" htmlFor="document-query">
          {isEn ? "Search publications" : "Cari publikasi"}
          <input id="document-query" name="q" type="search" placeholder={isEn ? "Search by title or keyword" : "Cari berdasarkan judul atau kata kunci"} maxLength={200} />
        </label>
        <div className="filter-grid">
          <label className="field" htmlFor="document-year">{isEn ? "Year" : "Tahun"}<input id="document-year" name="year" type="number" min="1" placeholder="e.g. 2024" /></label>
          <label className="field" htmlFor="document-topic">{isEn ? "Topic / subject" : "Topik / subjek"}<input id="document-topic" name="topic" placeholder={isEn ? "e.g. Population" : "mis. Kemiskinan"} maxLength={200} /></label>
        </div>
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? (isEn ? "Searching..." : "Mencari...") : (isEn ? "Search publications" : "Cari publikasi")}
        </button>
      </form>
      <section className="results-region" aria-labelledby="results-title" aria-live="polite" aria-busy={loading}>
        <div className="panel-heading">
          <h2 id="results-title">{isEn ? "Results" : "Hasil"}</h2>
          <span className="state-badge">
            {loading ? (isEn ? "Loading" : "Memuat") : error ? (isEn ? "Error" : "Kendala") : results ? (isEn ? `${results.totalCount} found` : `${results.totalCount} ditemukan`) : (isEn ? "Ready" : "Siap")}
          </span>
        </div>
        {loading ? <p className="state-message" role="status">{isEn ? "Retrieving publications..." : "Mengambil publikasi..."}</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {!loading && !error && !results ? <p className="state-message">{isEn ? "Enter at least one search criterion to find indexed BPS publications." : "Masukkan setidaknya satu kriteria pencarian untuk menemukan publikasi BPS."}</p> : null}
        {results?.items.length === 0 ? <p className="state-message">{isEn ? "No publications matched these search criteria." : "Tidak ada publikasi yang cocok dengan kriteria pencarian ini."}</p> : null}
        {results?.items.length ? (
          <div className="document-results">
            {results.items.map((document) => <DocumentResult key={document.documentId} document={document} isEn={isEn} />)}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function DocumentResult({ document, isEn }: { document: DocumentSearchItem; isEn: boolean }) {
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
        <div><dt>{isEn ? "Year" : "Tahun"}</dt><dd>{document.publicationYear}</dd></div>
        <div><dt>{isEn ? "Region" : "Wilayah"}</dt><dd>{document.region}</dd></div>
        <div><dt>{isEn ? "Region level" : "Tingkat"}</dt><dd>{document.regionLevel}</dd></div>
        {document.topic ? <div><dt>{isEn ? "Topic" : "Topik"}</dt><dd>{document.topic}</dd></div> : null}
      </dl>
      {safeSource
        ? <a className="source-link" href={safeSource} target="_blank" rel="noreferrer">{isEn ? "View source publication" : "Buka publikasi sumber"}</a>
        : <p className="source-placeholder">{isEn ? "Source link unavailable." : "Tautan publikasi tidak tersedia."}</p>}
    </article>
  );
}
