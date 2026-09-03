"use client";

import Link from "next/link";
import { useAuth } from "@/components/auth-provider";
import { RingkasLogo } from "@/components/ringkas-logo";
import { BpsLogo } from "@/components/bps-logo";
import { useInterfaceLanguage } from "@/lib/language";

export default function HomePage() {
  const { isAuthenticated } = useAuth();
  const [language] = useInterfaceLanguage();

  const isEn = language === "en";

  return (
    <div className="home-page">
      <section className="home-card" aria-labelledby="home-title">
        <div className="home-hero">
          <div className="home-copy">
            <p className="eyebrow">
              {isEn ? "Source-Grounded Statistical Assistant" : "Asisten Statistik Berbasis Sumber"}
            </p>
            <h1 id="home-title">
              <span className="home-title-brand">RINGKAS</span>
              <span className="home-title-expansion">
                {isEn
                  ? "National Generative Information Retrieval for Statistical Archives"
                  : "Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik"}
              </span>
              <span className="home-title-tagline">
                {isEn ? (
                  <>Evidence first.<br />Then believe.</>
                ) : (
                  <>Bukti dulu.<br />Baru percaya.</>
                )}
              </span>
            </h1>
            <p className="home-description">
              {isEn
                ? "RINGKAS helps you discover and comprehend BPS DKI Jakarta publications. Every substantive answer requires authentic citations that can be verified directly on the source page."
                : "RINGKAS membantu Anda menemukan dan memahami publikasi BPS DKI Jakarta. Setiap jawaban substantif wajib memiliki sitasi otentik yang dapat Anda verifikasi langsung ke halaman sumber."}
            </p>
            <div className="home-actions">
              <Link className="primary-button ds-btn-primary" href="/chat">
                {isAuthenticated
                  ? (isEn ? "Open Research Workspace" : "Buka Ruang Riset")
                  : (isEn ? "Start Research" : "Mulai Riset")}
              </Link>
              {!isAuthenticated ? (
                <Link className="secondary-button" href="/login">
                  {isEn ? "Sign In to Save" : "Masuk untuk Menyimpan"}
                </Link>
              ) : null}
            </div>
            <p className="home-access-note">
              {isAuthenticated
                ? (isEn
                    ? "Research workspace, document search, and question history ready."
                    : "Ruang riset, pencarian dokumen, dan riwayat pertanyaan siap digunakan.")
                : (isEn
                    ? "Guest mode available for 1 research query with publication citations."
                    : "Mode tamu tersedia untuk 1 kali pertanyaan riset beserta sitasi publikasi.")}
            </p>
          </div>
          <div className="home-visual" aria-label={isEn ? "RINGKAS citation preview example" : "Contoh tampilan citation RINGKAS"}>
            <div className="evidence-preview">
              <div className="preview-top">
                <span>RINGKAS / EVIDENCE SPEC</span>
                <b>{isEn ? "VERIFIED CITATION" : "SITASI SAH"}</b>
              </div>
              <div className="preview-rule" />
              <p className="preview-question">
                {isEn
                  ? "How do you find statistics you can truly rely on?"
                  : "Bagaimana menemukan statistik yang dapat dipertanggungjawabkan?"}
              </p>
              <div className="preview-answer">
                <span>[01]</span>
                <p>
                  {isEn
                    ? "Answers are synthesized directly from verified BPS publication text extracts, complete with page metadata and authentic quotes."
                    : "Jawaban disusun langsung dari ekstrak teks publikasi BPS, lengkap dengan metadata halaman dan kutipan asli."}
                </p>
              </div>
              <div className="preview-source">
                <small>VERIFIED SOURCE</small>
                <strong>BPS Provinsi DKI Jakarta</strong>
                <span>{isEn ? "Region · Year · Page · Excerpt" : "Wilayah · Tahun · Halaman · Excerpt"}</span>
              </div>
              <div className="preview-bottom">
                <span>{isEn ? "Verified Citation" : "Sitasi Terverifikasi"}</span>
                <i aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>
        <div className="home-proof" aria-label={isEn ? "RINGKAS Principles" : "Prinsip RINGKAS"}>
          <span>
            <b>{isEn ? "Publication-Grounded" : "Berbasis Publikasi"}</b>
            <small>
              {isEn
                ? "Answers synthesized purely from indexed BPS documents without fabricated statistics."
                : "Jawaban murni dari corpus BPS yang terindeks tanpa karangan statistik."}
            </small>
          </span>
          <span>
            <b>{isEn ? "Transparent Citations" : "Sitasi Transparan"}</b>
            <small>
              {isEn
                ? "Direct access to metadata, page numbers, paragraph quotes, and PDF source links."
                : "Akses metadata, nomor halaman, cuplikan paragraf, dan link sumber PDF."}
            </small>
          </span>
          <span>
            <b>{isEn ? "Honest Limitations" : "Batasan Jujur"}</b>
            <small>
              {isEn
                ? "RINGKAS refuses to answer substantive claims when available evidence is insufficient."
                : "RINGKAS menolak menjawab secara terukur apabila bukti belum mencukupi."}
            </small>
          </span>
        </div>
        <div className="home-attribution">
          <div className="home-attribution-badge">
            <BpsLogo width={40} height={31} className="bps-attribution-img" />
            <div>
              <p className="eyebrow">{isEn ? "Data Source Attribution" : "Apresiasi Sumber Data"}</p>
              <strong>{isEn ? "BPS - Statistics Indonesia" : "Badan Pusat Statistik Republik Indonesia"}</strong>
            </div>
          </div>
          <p className="home-attribution-note">
            {isEn
              ? "All data, indicator definitions, and publication documents in this system originate from BPS Provinsi DKI Jakarta. RINGKAS is developed as an independent information retrieval system prioritizing citation transparency and page-level precision."
              : "Seluruh data, definisi indikator, dan dokumen publikasi dalam sistem ini bersumber dari Badan Pusat Statistik Provinsi DKI Jakarta. RINGKAS dikembangkan sebagai sistem temu-kembali informasi independen yang memprioritaskan transparansi kutipan dan akurasi rujukan halaman."}
          </p>
        </div>
        <div className="home-footer">
          <div className="home-footer-brand">
            <RingkasLogo size={20} className="footer-logo-svg" />
            <span>RINGKAS</span>
          </div>
          <p>
            {isEn
              ? "Statistical research guiding you from question to authentic evidence."
              : "Riset statistik yang membantu Anda bergerak dari pertanyaan ke bukti otentik."}
          </p>
          <b>{isEn ? "DKI JAKARTA / BPS PUBLICATIONS" : "DKI JAKARTA / PUBLIKASI BPS"}</b>
        </div>
      </section>
    </div>
  );
}
