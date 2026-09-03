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
  const [language] = useInterfaceLanguage();
  const headerLanguage = pathname === "/" ? "id" : language;
  const labels = headerLanguage === "id"
    ? { home: "Beranda", chat: "Chat", documents: "Dokumen", admin: "Admin", checking: "Memeriksa sesi...", subtitle: "Riset BPS dengan bukti", bpsCredit: "Korpus BPS DKI" }
    : { home: "Home", chat: "Chat", documents: "Documents", admin: "Admin", checking: "Checking session...", subtitle: "BPS research, with evidence", bpsCredit: "BPS DKI Corpus" };
  const visibleLinks = [{ href: "/", label: labels.home }, { href: "/chat", label: labels.chat }];
  if (isAuthenticated) {
    visibleLinks.push({ href: "/documents", label: labels.documents });
    if (hasAnyRole("admin", "system_maintainer")) visibleLinks.push({ href: "/admin", label: labels.admin });
  } else if (!isLoading) {
    visibleLinks.push(
      { href: "/login", label: headerLanguage === "id" ? "Masuk" : "Sign in" },
      { href: "/register", label: headerLanguage === "id" ? "Daftar" : "Register" }
    );
  }

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <div className="brand-group">
          <Link className="brand" href="/" aria-label="Beranda RINGKAS">
            <RingkasLogo size={28} className="brand-logo-svg" />
            <span className="brand-title">RINGKAS</span>
          </Link>
          <div className="brand-divider" aria-hidden="true" />
          <div className="brand-bps-credit" title="Publikasi dan arsip bersumber dari Badan Pusat Statistik Republik Indonesia">
            <BpsLogo width={20} height={16} className="bps-header-logo" />
            <span className="bps-credit-text">{labels.bpsCredit}</span>
          </div>
        </div>
        <nav className="nav" aria-label="Main navigation">
          {visibleLinks.map(({ href, label }) => <Link aria-current={pathname === href ? "page" : undefined} className={`nav-link${pathname === href ? " active" : ""}`} href={href} key={href}>{label}</Link>)}
          {isAuthenticated && <UserAccountMenu />}
        </nav>
      </div>
    </header>
  );
}
