"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./auth-provider";
import { useInterfaceLanguage } from "@/lib/language";

export function SiteHeader() {
  const pathname = usePathname();
  const { isLoading, isAuthenticated, hasAnyRole } = useAuth();
  const [language] = useInterfaceLanguage();
  const headerLanguage = pathname === "/" ? "id" : language;
  const labels = headerLanguage === "id"
    ? { home: "Beranda", chat: "Chat", documents: "Dokumen", admin: "Admin", checking: "Memeriksa sesi...", subtitle: "Riset BPS dengan bukti" }
    : { home: "Home", chat: "Chat", documents: "Documents", admin: "Admin", checking: "Checking session...", subtitle: "BPS research, with evidence" };
  const visibleLinks = [{ href: "/", label: labels.home }, { href: "/chat", label: labels.chat }];
  if (isAuthenticated) visibleLinks.push({ href: "/documents", label: labels.documents });
  if (hasAnyRole("admin", "system_maintainer")) visibleLinks.push({ href: "/admin", label: labels.admin });
  if (!isLoading && !isAuthenticated) visibleLinks.push(
    { href: "/login", label: headerLanguage === "id" ? "Masuk" : "Sign in" }, { href: "/register", label: headerLanguage === "id" ? "Daftar" : "Register" }
  );

  return <>
    <header className="site-header">
      <div className="site-header-inner">
        <Link className="brand" href="/"><span className="brand-mark" aria-hidden="true">R</span><span className="brand-block"><strong>RINGKAS</strong><small>{labels.subtitle}</small></span></Link>
        <nav className="nav" aria-label="Main navigation">
          {visibleLinks.map(({ href, label }) => <Link aria-current={pathname === href ? "page" : undefined} className={`nav-link${pathname === href ? " active" : ""}`} href={href} key={href}>{label}</Link>)}
          {isLoading ? <span className="nav-link nav-link-static">{labels.checking}</span> : null}
        </nav>
      </div>
    </header>
  </>;
}
