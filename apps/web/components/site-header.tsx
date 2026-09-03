"use client";

import { useState, useEffect } from "react";
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
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [mobileOpen]);

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
          <div className="nav-links-desktop">
            {visibleLinks.map(({ href, label }) => <Link aria-current={pathname === href ? "page" : undefined} className={`nav-link${pathname === href ? " active" : ""}`} href={href} key={href}>{label}</Link>)}
          </div>
          <div className="header-language-control">
            <span className="language-pill-display" aria-hidden="true">
              <GlobeIcon size={16} className="language-globe-icon" />
              <span className="language-current-label">{language.toUpperCase()}</span>
              <ChevronDownIcon size={12} className="language-chevron" />
            </span>
            <select
              className="language-native-select"
              value={language}
              aria-label="Pilih Bahasa / Select Language"
              onChange={(event) => changeLanguage(event.target.value as "id" | "en")}
            >
              <option value="id">Bahasa Indonesia (ID)</option>
              <option value="en">English (EN)</option>
            </select>
          </div>
          {isAuthenticated && <UserAccountMenu />}
          <button
            className="mobile-menu-toggle"
            type="button"
            aria-label={mobileOpen ? (language === "id" ? "Tutup menu" : "Close menu") : (language === "id" ? "Buka menu" : "Open menu")}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((prev) => !prev)}
          >
            {mobileOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
          </button>
        </nav>
      </div>

      {mobileOpen && (
        <div className="mobile-nav-backdrop" onClick={() => setMobileOpen(false)}>
          <aside
            className="mobile-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Navigasi"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-nav-header">
              <div className="brand">
                <RingkasLogo size={28} className="brand-logo-svg" />
                <span className="brand-title">RINGKAS</span>
              </div>
              <button
                className="mobile-nav-close"
                type="button"
                aria-label={language === "id" ? "Tutup menu" : "Close menu"}
                onClick={() => setMobileOpen(false)}
              >
                <CloseIcon size={18} />
              </button>
            </div>
            <div className="mobile-nav-links">
              {visibleLinks.map(({ href, label }) => (
                <Link
                  aria-current={pathname === href ? "page" : undefined}
                  className={`mobile-nav-link${pathname === href ? " active" : ""}`}
                  href={href}
                  key={href}
                  onClick={() => setMobileOpen(false)}
                >
                  <span>{label}</span>
                  {pathname === href && <span className="mobile-nav-dot" aria-hidden="true" />}
                </Link>
              ))}
            </div>
            <div className="mobile-nav-footer">
              <div className="mobile-bps-badge">
                <BpsLogo width={22} height={18} />
                <span>{language === "id" ? "Korpus BPS DKI Jakarta" : "BPS DKI Jakarta Corpus"}</span>
              </div>
            </div>
          </aside>
        </div>
      )}
    </header>
  );
}

function GlobeIcon({ className, size = 16 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
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

function ChevronDownIcon({ className, size = 12 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function MenuIcon({ className, size = 20 }: { className?: string; size?: number }) {
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
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  );
}

function CloseIcon({ className, size = 20 }: { className?: string; size?: number }) {
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
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
