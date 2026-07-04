"use client";

import { useState } from "react";
import { apiRequest } from "@/lib/api-client";

interface ChatCitation {
  document_id: string;
  chunk_id: string;
  title: string;
  year: number;
  region: string;
  page_start: number | null;
  page_end: number | null;
  source_url: string;
  snippet: string;
}

interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  source_sufficiency: "sufficient" | "partial" | "insufficient";
  provider: string | null;
  session_id?: string | null;
}

const sufficiencyLabels = {
  sufficient: "Sufficient evidence",
  partial: "Partial evidence",
  insufficient: "Insufficient evidence"
} as const;

export function ChatForm() {
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = String(new FormData(form).get("message") ?? "").trim();

    if (!message) {
      setError("Enter a question before submitting.");
      setResponse(null);
      return;
    }

    setLoading(true);
    setError("");
    setResponse(null);
    try {
      const nextResponse = await apiRequest<ChatResponse>("/api/chat", {
        method: "POST",
        body: { message, session_id: sessionId }
      });
      setResponse(nextResponse);
      if (nextResponse.session_id) setSessionId(nextResponse.session_id);
      form.reset();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Chat is unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const limitation = response?.source_sufficiency === "partial"
    ? "The available sources only partially support this answer. Treat it as limited and verify the cited passages before relying on it."
    : response?.source_sufficiency === "insufficient"
      ? "The available sources are not sufficient for a substantive answer. Any sources below are the closest matches, not proof of the requested claim."
      : null;

  return (
    <div className="feature-stack">
      <form className="question-form" onSubmit={handleSubmit}>
        <label className="field" htmlFor="question">
          Your question
          <textarea
            id="question"
            name="message"
            rows={4}
            maxLength={2000}
            required
            disabled={loading}
            placeholder="Example: What was Indonesia's population according to the latest available publication?"
          />
        </label>
        <p className="field-hint">Maximum 2,000 characters.</p>
        <button className="primary-button" type="submit" disabled={loading}>{loading ? "Finding evidence..." : "Ask RINGKAS"}</button>
      </form>

      <section className="answer-panel" aria-labelledby="answer-title" aria-live="polite" aria-busy={loading}>
        <div className="panel-heading">
          <h2 id="answer-title">Answer</h2>
          <span className={`state-badge${response ? ` sufficiency-${response.source_sufficiency}` : ""}`}>
            {loading ? "Loading" : error ? "Error" : response ? sufficiencyLabels[response.source_sufficiency] : "Ready"}
          </span>
        </div>
        {loading ? <p className="state-message" role="status">Searching the indexed BPS publications and checking the evidence...</p> : null}
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {!loading && !error && !response ? <p className="state-message">Ask a question to receive an evidence-grounded answer.</p> : null}
        {response ? <p className="answer-text">{response.answer || "No answer was returned."}</p> : null}
        {response?.provider ? <p className="provider-note">Provider: {response.provider}</p> : null}
      </section>

      {limitation ? <p className={`limitation-note limitation-${response?.source_sufficiency}`} role="alert"><strong>Evidence limitation:</strong> {limitation}</p> : null}

      {response ? (
        <section className="citation-panel" aria-labelledby="citation-title">
          <div className="panel-heading">
            <h2 id="citation-title">{response.source_sufficiency === "insufficient" ? "Closest sources" : "Sources and citations"}</h2>
            <span className="state-badge">{response.citations.length} source{response.citations.length === 1 ? "" : "s"}</span>
          </div>
          {response.citations.length ? (
            <div className="citation-list">
              {response.citations.map((citation, index) => <Citation key={citation.chunk_id} citation={citation} index={index} />)}
            </div>
          ) : <p className="state-message">No source citations were returned.</p>}
        </section>
      ) : null}
    </div>
  );
}

function Citation({ citation, index }: { citation: ChatCitation; index: number }) {
  let safeSource: string | null = null;
  try {
    const url = new URL(citation.source_url);
    if (url.protocol === "https:" || url.protocol === "http:") safeSource = citation.source_url;
  } catch {
    // Invalid source URLs are shown as unavailable rather than rendered as links.
  }

  const page = citation.page_start === null && citation.page_end === null
    ? null
    : citation.page_start === citation.page_end || citation.page_end === null
      ? `Page ${citation.page_start}`
      : citation.page_start === null
        ? `Page ${citation.page_end}`
        : `Pages ${citation.page_start}-${citation.page_end}`;

  return (
    <article className="citation-card">
      <p className="citation-label">[{index + 1}]</p>
      <h3>{citation.title}</h3>
      <p className="citation-meta">{[String(citation.year), citation.region, page].filter(Boolean).join(" · ")}</p>
      <blockquote>{citation.snippet}</blockquote>
      {safeSource
        ? <a className="source-link" href={safeSource} target="_blank" rel="noreferrer">View source publication</a>
        : <p className="source-placeholder">Source link unavailable.</p>}
    </article>
  );
}
