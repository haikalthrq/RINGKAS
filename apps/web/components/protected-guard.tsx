"use client";

import Link from "next/link";
import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./auth-provider";

export function ProtectedGuard({ children }: { children: ReactNode }) {
  const { isLoading, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const query = window.location.search.slice(1);
      router.replace(`/login?from=${encodeURIComponent(`${pathname}${query ? `?${query}` : ""}`)}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  if (isLoading || !isAuthenticated) return <StatusCard eyebrow="Session" title="Checking your session" />;
  return children;
}

export function AdminRoleGuard({ children }: { children: ReactNode }) {
  const { hasAnyRole } = useAuth();

  if (!hasAnyRole("admin", "system_maintainer")) {
    return <section className="page-card"><p className="eyebrow">403</p><h1>Access denied</h1><p>This area is limited to admin and system maintainer roles.</p><Link className="inline-link" href="/chat">Go to chat</Link></section>;
  }

  return children;
}

function StatusCard({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <section className="page-card status-card" aria-live="polite"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>Loading account state before showing this page.</p></section>;
}
