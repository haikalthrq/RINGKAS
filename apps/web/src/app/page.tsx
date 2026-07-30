"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/auth-provider";
import { useInterfaceLanguage } from "@/lib/language";

export default function HomePage() {
  const [language] = useInterfaceLanguage();
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const labels = language === "id"
    ? {
      kicker: "Asisten statistik berbasis sumber",
      scope: "Publikasi BPS DKI Jakarta",
      title: "Pahami statistik dengan bukti yang bisa diperiksa.",
      description: "RINGKAS membantu kamu mencari dan memahami publikasi BPS DKI Jakarta. Setiap jawaban berangkat dari dokumen terindeks, menampilkan citation, dan menyatakan saat bukti belum cukup.",
      start: "Coba RINGKAS",
      signIn: "Masuk untuk menyimpan riwayat",
      accessNote: "Chat tamu tersedia untuk satu pertanyaan. Pencarian dokumen dan riwayat tersimpan tersedia setelah masuk.",
      principle: "Yang dijaga RINGKAS",
      steps: [["Berbasis publikasi", "Jawaban hanya berasal dari corpus BPS yang tersedia."], ["Citation terlihat", "Buka metadata, halaman, excerpt, dan URL sumber."], ["Batasan jujur", "RINGKAS tidak mengisi celah ketika bukti belum cukup."]]
    }
    : {
      kicker: "Source-grounded statistics assistant",
      scope: "BPS DKI Jakarta publications",
      title: "Understand statistics with evidence you can check.",
      description: "RINGKAS helps you search and understand BPS DKI Jakarta publications. Every answer starts from indexed documents, shows its citations, and says when the evidence is not enough.",
      start: "Try RINGKAS",
      signIn: "Sign in for history",
      accessNote: "Guest chat is available for one question. Document search and saved history are available after sign-in.",
      principle: "What RINGKAS protects",
      steps: [["Publication-based", "Answers come only from the available BPS corpus."], ["Citations visible", "Open source metadata, pages, excerpts, and URLs."], ["Honest limits", "RINGKAS does not fill gaps when evidence is insufficient."]]
    };

  useEffect(() => {
    if (!authLoading && isAuthenticated) router.replace("/chat");
  }, [authLoading, isAuthenticated, router]);

  if (authLoading || isAuthenticated) {
    return <section className="page-card status-card" aria-live="polite"><p className="eyebrow">RINGKAS</p><h1>{language === "id" ? "Membuka ruang riset..." : "Opening the research workspace..."}</h1></section>;
  }

  return (
    <section className="home-card" aria-labelledby="home-title">
      <div className="home-kicker"><span>RINGKAS / BPS</span><span className="home-scope"><i aria-hidden="true" /> {labels.scope}</span></div>
      <div className="home-copy">
        <p className="eyebrow">{labels.kicker}</p>
        <h1 id="home-title">{labels.title}</h1>
        <p>{labels.description}</p>
      </div>
      <div className="home-actions">
        <Link className="primary-button" href="/chat">{labels.start}</Link>
        <Link className="secondary-button" href="/login">{labels.signIn}</Link>
      </div>
      <p className="home-access-note">{labels.accessNote}</p>
      <div className="home-proof" aria-label={labels.principle}>
        {labels.steps.map(([title, description]) => <span key={title}><b>{title}</b><small>{description}</small></span>)}
      </div>
    </section>
  );
}
