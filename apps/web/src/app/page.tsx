"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

export default function HomePage() {
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  if (authLoading) {
    return <section className="page-card status-card" aria-live="polite"><p className="eyebrow">RINGKAS</p><h1>Membuka ruang riset...</h1></section>;
  }

  return (
    <div className="home-page">
      <section className="home-card" aria-labelledby="home-title">
        <div className="home-kicker"><span>RINGKAS / BPS</span><span className="home-scope"><i aria-hidden="true" /> Publikasi DKI Jakarta</span></div>
        <div className="home-hero">
          <div className="home-copy">
            <p className="eyebrow">Asisten statistik berbasis sumber</p>
            <h1 id="home-title"><span className="home-title-brand">RINGKAS</span><span className="home-title-expansion">Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik</span><span className="home-title-tagline">Bukti dulu.<br />Baru percaya.</span></h1>
            <p className="home-description">RINGKAS membantu kamu mencari dan memahami publikasi BPS DKI Jakarta. Jawaban disusun dari dokumen terindeks, lalu dikembalikan ke sumber yang bisa kamu periksa.</p>
            <div className="home-actions">
              <Link className="primary-button" href="/chat">{isAuthenticated ? "Buka ruang riset" : "Mulai riset"}</Link>
              {!isAuthenticated ? <Link className="secondary-button" href="/login">Masuk untuk menyimpan</Link> : null}
            </div>
            <p className="home-access-note">{isAuthenticated ? "Ruang riset, pencarian dokumen, dan riwayat pertanyaan tersedia dari navigation." : "Chat tamu tersedia untuk satu pertanyaan. Pencarian dokumen dan riwayat tersimpan tersedia setelah masuk."}</p>
          </div>
          <div className="home-visual" aria-label="Contoh tampilan citation RINGKAS">
            <div className="evidence-preview">
              <div className="preview-top"><span>RINGKAS / CONTOH CITATION</span><b>BUKTI</b></div>
              <div className="preview-rule" />
              <p className="preview-question">Bagaimana menemukan statistik yang bisa dipertanggungjawabkan?</p>
              <div className="preview-answer"><span>[01]</span><p>Jawaban ringkas dari publikasi BPS, dengan halaman dan konteks yang bisa dibuka.</p></div>
              <div className="preview-source"><small>SUMBER</small><strong>Publikasi BPS DKI Jakarta</strong><span>Wilayah · Tahun · Halaman · Excerpt</span></div>
              <div className="preview-bottom"><span>Citation terbuka</span><i aria-hidden="true" /></div>
            </div>
          </div>
        </div>
        <div className="home-proof" aria-label="Prinsip RINGKAS">
          <span><b>Berbasis publikasi</b><small>Jawaban hanya berasal dari corpus BPS yang tersedia.</small></span>
          <span><b>Citation terlihat</b><small>Buka metadata, halaman, excerpt, dan URL sumber.</small></span>
          <span><b>Batasan jujur</b><small>RINGKAS tidak mengisi celah ketika bukti belum cukup.</small></span>
        </div>
        <div className="home-footer"><span>RINGKAS</span><p>Riset statistik yang membantu kamu bergerak dari pertanyaan ke bukti.</p><b>DKI JAKARTA / PUBLIKASI BPS</b></div>
      </section>
    </div>
  );
}
