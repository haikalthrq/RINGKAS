"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

export default function HomePage() {
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  if (authLoading) {
    return (
      <section className="page-card status-card" aria-live="polite">
        <p className="eyebrow">RINGKAS / BPS</p>
        <h1>Membuka ruang riset...</h1>
      </section>
    );
  }

  return (
    <div className="home-page">
      <section className="home-card" aria-labelledby="home-title">
        <div className="home-kicker">
          <span>RINGKAS / BPS</span>
          <span className="home-scope">
            <i aria-hidden="true" /> Corpus Publikasi DKI Jakarta
          </span>
        </div>
        <div className="home-hero">
          <div className="home-copy">
            <p className="eyebrow">Asisten Statistik Berbasis Sumber</p>
            <h1 id="home-title">
              <span className="home-title-brand">RINGKAS</span>
              <span className="home-title-expansion">
                Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik
              </span>
              <span className="home-title-tagline">
                Bukti dulu.<br />Baru percaya.
              </span>
            </h1>
            <p className="home-description">
              RINGKAS membantu Anda menemukan dan memahami publikasi BPS DKI Jakarta. Setiap jawaban substantif wajib memiliki sitasi otentik yang dapat Anda verifikasi langsung ke halaman sumber.
            </p>
            <div className="home-actions">
              <Link className="primary-button ds-btn-primary" href="/chat">
                {isAuthenticated ? "Buka Ruang Riset" : "Mulai Riset"}
              </Link>
              {!isAuthenticated ? (
                <Link className="secondary-button" href="/login">
                  Masuk untuk Menyimpan
                </Link>
              ) : null}
            </div>
            <p className="home-access-note">
              {isAuthenticated
                ? "Ruang riset, pencarian dokumen, dan riwayat pertanyaan siap digunakan."
                : "Mode tamu tersedia untuk 1 kali pertanyaan riset beserta sitasi publikasi."}
            </p>
          </div>
          <div className="home-visual" aria-label="Contoh tampilan citation RINGKAS">
            <div className="evidence-preview">
              <div className="preview-top">
                <span>RINGKAS / EVIDENCE SPEC</span>
                <b>SITASI SAH</b>
              </div>
              <div className="preview-rule" />
              <p className="preview-question">
                Bagaimana menemukan statistik yang dapat dipertanggungjawabkan?
              </p>
              <div className="preview-answer">
                <span>[01]</span>
                <p>
                  Jawaban disusun langsung dari ekstrak teks publikasi BPS, lengkap dengan metadata halaman dan kutipan asli.
                </p>
              </div>
              <div className="preview-source">
                <small>VERIFIED SOURCE</small>
                <strong>BPS Provinsi DKI Jakarta</strong>
                <span>Wilayah · Tahun · Halaman · Excerpt</span>
              </div>
              <div className="preview-bottom">
                <span>Sitasi Terverifikasi</span>
                <i aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>
        <div className="home-proof" aria-label="Prinsip RINGKAS">
          <span>
            <b>Berbasis Publikasi</b>
            <small>Jawaban murni dari corpus BPS yang terindeks tanpa karangan statistik.</small>
          </span>
          <span>
            <b>Sitasi Transparan</b>
            <small>Akses metadata, nomor halaman, cuplikan paragraf, dan link sumber PDF.</small>
          </span>
          <span>
            <b>Batasan Jujur</b>
            <small>RINGKAS menolak menjawab secara terukur apabila bukti belum mencukupi.</small>
          </span>
        </div>
        <div className="home-footer">
          <span>RINGKAS</span>
          <p>Riset statistik yang membantu Anda bergerak dari pertanyaan ke bukti otentik.</p>
          <b>DKI JAKARTA / PUBLIKASI BPS</b>
        </div>
      </section>
    </div>
  );
}
