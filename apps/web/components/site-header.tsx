"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./auth-provider";

const links = [{ href: "/", label: "Home" }, { href: "/chat", label: "Chat" }];

export function SiteHeader() {
  const pathname = usePathname();
  const { isLoading, isAuthenticated, currentUser, hasAnyRole } = useAuth();
  const visibleLinks = [...links];
  if (isAuthenticated) visibleLinks.push({ href: "/documents", label: "Documents" });
  if (hasAnyRole("admin", "system_maintainer")) visibleLinks.push({ href: "/admin", label: "Admin" });
  if (!isLoading && !isAuthenticated) visibleLinks.push(
    { href: "/login", label: "Login" }, { href: "/register", label: "Register" }
  );

  return <>
    <header className="site-header">
      <div className="brand-block"><Link className="brand" href="/">RINGKAS</Link><p className="brand-subtitle">BPS publication Q&amp;A</p></div>
      <nav className="nav" aria-label="Main navigation">
        {visibleLinks.map(({ href, label }) => <Link className={`nav-link${pathname === href ? " active" : ""}`} href={href} key={href}>{label}</Link>)}
        {isLoading ? <span className="nav-link nav-link-static">Loading session...</span> : null}
      </nav>
    </header>
    {currentUser ? <p className="session-note">Signed in as {currentUser.email ?? "user"}</p> : null}
  </>;
}
