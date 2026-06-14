import { DocumentSearch } from "@/components/documents/document-search";

export default function DocumentsPage() {
  return (
    <section className="page-card documents-page" aria-labelledby="documents-title">
      <p className="eyebrow">Documents</p>
      <h1 id="documents-title">Find a BPS publication</h1>
      <p className="page-intro">Search and metadata results will be connected after the document search API is ready.</p>
      <DocumentSearch />
    </section>
  );
}
