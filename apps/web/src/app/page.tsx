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
              {isEn ? "Statistical Retrieval System" : "Sistem Penelusuran Statistik"}
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
                  <>Ground every statistic<br />in official publications.</>
                ) : (
                  <>Rujuk data statistik<br />langsung ke dokumen aslinya.</>
                )}
              </span>
            </h1>
            <p className="home-description">
              {isEn
                ? "RINGKAS indexes BPS DKI Jakarta publications so you can query regional statistics and inspect the exact page, table, and paragraph behind every claim."
                : "RINGKAS mengindeks publikasi BPS DKI Jakarta agar Anda dapat menelusuri data statistik daerah dan memeriksa langsung halaman, tabel, serta paragraf sumbernya."}
            </p>
            <div className="home-actions">
              <Link className="primary-button ds-btn-primary" href="/chat">
                {isAuthenticated
                  ? (isEn ? "Open Workspace" : "Buka Ruang Riset")
                  : (isEn ? "Start Querying" : "Mulai Penelusuran")}
              </Link>
              {!isAuthenticated ? (
                <Link className="secondary-button" href="/login">
                  {isEn ? "Sign In" : "Masuk"}
                </Link>
              ) : null}
            </div>
            <p className="home-access-note">
              {isAuthenticated
                ? (isEn
                    ? "Saved chats, document search, and query history are enabled."
                    : "Riwayat pertanyaan dan penelusuran dokumen tersimpan di akun Anda.")
                : (isEn
                    ? "Guest mode allows 1 test query with verified citations."
                    : "Mode tamu tersedia untuk 1 kali pertanyaan beserta rujukan dokumen.")}
            </p>
          </div>
          <div className="home-visual" aria-label={isEn ? "Sample citation preview" : "Pratinjau contoh sitasi"}>
            <div className="evidence-preview">
              <div className="preview-top">
                <span>{isEn ? "SAMPLE CITATION" : "CONTOH SITASI"}</span>
                <b>{isEn ? "PAGE 14" : "HALAMAN 14"}</b>
              </div>
              <div className="preview-rule" />
              <p className="preview-question">
                {isEn
                  ? "What was the poverty line in DKI Jakarta in September 2024?"
                  : "Berapa Garis Kemiskinan di DKI Jakarta pada September 2024?"}
              </p>
              <div className="preview-answer">
                <span>[01]</span>
                <p>
                  {isEn
                    ? "The poverty line for DKI Jakarta in September 2024 stood at IDR 826,315 per capita per month, an increase of 2.14% compared to March 2024."
                    : "Garis Kemiskinan DKI Jakarta pada September 2024 tercatat sebesar Rp826.315 per kapita per bulan, naik 2,14% dibanding Maret 2024."}
                </p>
              </div>
              <div className="preview-source">
                <small>{isEn ? "SOURCE PUBLICATION" : "PUBLIKASI SUMBER"}</small>
                <strong>{isEn ? "BPS DKI Jakarta Province" : "BPS Provinsi DKI Jakarta"}</strong>
                <span>{isEn ? "Poverty Profile in DKI Jakarta · Sep 2024 · p. 14" : "Profil Kemiskinan di DKI Jakarta · Sep 2024 · hal. 14"}</span>
              </div>
              <div className="preview-bottom">
                <span>{isEn ? "Verified from publication text" : "Terverifikasi dari teks publikasi"}</span>
                <i aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>
        <div className="home-proof" aria-label={isEn ? "System standards" : "Standar sistem"}>
          <span>
            <b>{isEn ? "Indexed Corpus" : "Korpus Terindeks"}</b>
            <small>
              {isEn
                ? "Extracted text and metadata from official BPS regional releases."
                : "Teks dan metadata diekstrak dari publikasi resmi rilis BPS daerah."}
            </small>
          </span>
          <span>
            <b>{isEn ? "Page-Level Citations" : "Sitasi Nomor Halaman"}</b>
            <small>
              {isEn
                ? "Every substantive claim links to the document title, page number, and original quote."
                : "Setiap klaim data memuat judul publikasi, nomor halaman, dan kutipan kalimat aslinya."}
            </small>
          </span>
          <span>
            <b>{isEn ? "Refusal on Weak Evidence" : "Penolakan Bukti Lemah"}</b>
            <small>
              {isEn
                ? "The system refuses to generate statistical answers when retrieved evidence is insufficient."
                : "Sistem menolak memberikan angka jika bukti dokumen yang ditemukan belum mencukupi."}
            </small>
          </span>
        </div>
        <div className="home-attribution">
          <div className="home-attribution-badge">
            <BpsLogo width={40} height={31} className="bps-attribution-img" />
            <div>
              <p className="eyebrow">{isEn ? "Data Source" : "Sumber Data"}</p>
              <strong>{isEn ? "BPS - Statistics Indonesia" : "Badan Pusat Statistik Republik Indonesia"}</strong>
            </div>
          </div>
          <p className="home-attribution-note">
            {isEn
              ? "All statistical data and publications in this repository originate from BPS Provinsi DKI Jakarta. RINGKAS is an independent retrieval tool built to verify citations and page references."
              : "Seluruh publikasi dan data statistik dalam sistem ini bersumber dari Badan Pusat Statistik Provinsi DKI Jakarta. RINGKAS merupakan alat temu-kembali independen yang dirancang untuk memverifikasi rujukan halaman dan kutipan data."}
          </p>
        </div>
        <div className="home-footer">
          <div className="home-footer-brand">
            <RingkasLogo size={20} className="footer-logo-svg" />
            <span>RINGKAS</span>
          </div>
          <p>
            {isEn
              ? "Search and verify BPS statistical publications with citations."
              : "Temu-kembali dan verifikasi publikasi statistik BPS berbasis sitasi."}
          </p>
          <b>{isEn ? "DKI JAKARTA / BPS PUBLICATIONS" : "DKI JAKARTA / PUBLIKASI BPS"}</b>
        </div>
      </section>
    </div>
  );
}
