"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./auth-provider";
import { useInterfaceLanguage } from "@/lib/language";
import { RingkasLogo } from "./ringkas-logo";
import { BpsLogo } from "./bps-logo";
import { UserAccountMenu } from "./user-account-menu";

export function SiteHeader() {
  const pathname = usePathname();
  const { isLoading, isAuthenticated, hasAnyRole } = useAuth();
  const [language, changeLanguage] = useInterfaceLanguage();
  const labels = language === "id"
    ? { home: "Beranda", chat: "Chat", documents: "Dokumen", admin: "Admin", checking: "Memeriksa sesi...", bpsCredit: "Korpus BPS DKI" }
    : { home: "Home", chat: "Chat", documents: "Documents", admin: "Admin", checking: "Checking session...", bpsCredit: "BPS DKI Corpus" };
  const visibleLinks = [{ href: "/", label: labels.home }, { href: "/chat", label: labels.chat }];
  if (isAuthenticated) {
    visibleLinks.push({ href: "/documents", label: labels.documents });
    if (hasAnyRole("admin", "system_maintainer")) visibleLinks.push({ href: "/admin", label: labels.admin });
  } else if (!isLoading) {
    visibleLinks.push(
      { href: "/login", label: language === "id" ? "Masuk" : "Sign in" },
      { href: "/register", label: language === "id" ? "Daftar" : "Register" }
    );
  }

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <div className="brand-group">
          <Link className="brand" href="/" aria-label="Beranda RINGKAS">
            <RingkasLogo size={34} className="brand-logo-svg" />
            <span className="brand-title">RINGKAS</span>
          </Link>
          <div className="brand-divider" aria-hidden="true" />
          <div className="brand-bps-credit" title="Publikasi dan arsip bersumber dari Badan Pusat Statistik Republik Indonesia">
            <BpsLogo width={22} height={18} className="bps-header-logo" />
            <span className="bps-credit-text">{labels.bpsCredit}</span>
          </div>
        </div>
        <nav className="nav" aria-label="Main navigation">
          {visibleLinks.map(({ href, label }) => <Link aria-current={pathname === href ? "page" : undefined} className={`nav-link${pathname === href ? " active" : ""}`} href={href} key={href}>{label}</Link>)}
          <label className="language-control header-language-control">
            <span className="sr-only">Bahasa / Language</span>
            <GlobeIcon className="language-globe-icon" aria-hidden="true" />
            <select
              value={language}
              aria-label="Pilih Bahasa / Select Language"
              onChange={(event) => changeLanguage(event.target.value as "id" | "en")}
            >
              <option value="id">ID</option>
              <option value="en">EN</option>
            </select>
          </label>
          {isAuthenticated && <UserAccountMenu />}
        </nav>
      </div>
    </header>
  );
}

function GlobeIcon({ className, size = 15 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}
