"use client";

import { DocumentSearch } from "@/components/documents/document-search";
import { useInterfaceLanguage } from "@/lib/language";

export default function DocumentsPage() {
  const [language] = useInterfaceLanguage();
  const isEn = language === "en";

  return (
    <section className="page-card documents-page" aria-labelledby="documents-title">
      <p className="eyebrow">{isEn ? "Documents" : "Dokumen"}</p>
      <h1 id="documents-title">{isEn ? "Find a BPS Publication" : "Cari Publikasi BPS"}</h1>
      <p className="page-intro">
        {isEn
          ? "Search indexed BPS DKI Jakarta publications by title, year, or topic."
          : "Cari publikasi BPS DKI Jakarta yang terindeks berdasarkan judul, tahun, atau topik."}
      </p>
      <DocumentSearch />
    </section>
  );
}
