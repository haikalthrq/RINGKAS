"use client";

import { useState } from "react";

export function ChatForm() {
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  return (
    <div className="feature-stack">
      <form className="question-form" onSubmit={handleSubmit}>
        <label className="field" htmlFor="question">
          Your question
          <textarea id="question" name="question" rows={4} placeholder="Example: What is the latest population figure?" />
        </label>
        <button className="primary-button" type="submit">Submit question</button>
      </form>
      {submitted ? <p className="form-note" role="status">Submission preview only. No request was sent.</p> : null}
      <section className="answer-panel" aria-labelledby="answer-title" aria-live="polite">
        <div className="panel-heading"><h2 id="answer-title">Answer</h2><span className="state-badge">Empty</span></div>
        <p>No answer is available yet. Ask a question after backend integration is enabled.</p>
      </section>
      <div className="state-preview" aria-label="Answer state previews">
        <span>Pending: waiting for service</span><span>Error: service unavailable</span>
      </div>
      <section className="citation-panel" aria-labelledby="citation-title">
        <div className="panel-heading"><h2 id="citation-title">Sources and citations</h2><span className="state-badge">Placeholder</span></div>
        <p>Document title, year, region, page, source URL, and excerpt will appear here when evidence is retrieved.</p>
      </section>
      <p className="limitation-note" role="note"><strong>Evidence limitation:</strong> RINGKAS will not provide a substantive answer when retrieved evidence is insufficient. This preview contains no answer or citation.</p>
    </div>
  );
}
