"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth-provider";

export function UserAccountMenu() {
  const { currentUser, hasAnyRole, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const email = currentUser?.email || "Pengguna";
  const initial = email.charAt(0).toUpperCase();
  const isAdmin = hasAnyRole("admin", "system_maintainer");

  // Close dropdown on outside click or Escape key
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  async function handleLogout() {
    setIsLoggingOut(true);
    await logout();
  }

  return (
    <div className="user-menu-container" ref={menuRef}>
      <button
        type="button"
        className={`user-menu-trigger${isOpen ? " is-open" : ""}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label="Menu Akun Pengguna"
      >
        <span className="user-avatar" aria-hidden="true">{initial}</span>
        <span className="user-pill-email">{email}</span>
        <svg
          className="user-chevron"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <div className="user-menu-dropdown" role="menu">
          <div className="user-menu-header">
            <div className="user-avatar-large" aria-hidden="true">{initial}</div>
            <div className="user-header-info">
              <span className="user-header-email" title={email}>{email}</span>
              <span className={`user-role-badge ${isAdmin ? "admin" : "researcher"}`}>
                {isAdmin ? "Administrator" : "Peneliti Terdaftar"}
              </span>
            </div>
          </div>

          <div className="user-menu-divider" role="separator" />

          <div className="user-menu-links">
            <Link
              href="/chat"
              className="user-menu-item"
              role="menuitem"
              onClick={() => setIsOpen(false)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span>Ruang Riset</span>
            </Link>

            <Link
              href="/documents"
              className="user-menu-item"
              role="menuitem"
              onClick={() => setIsOpen(false)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
                <path d="M6 6h10" />
                <path d="M6 10h10" />
              </svg>
              <span>Dokumen Publikasi</span>
            </Link>

            {isAdmin && (
              <Link
                href="/admin"
                className="user-menu-item"
                role="menuitem"
                onClick={() => setIsOpen(false)}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <span>Panel Admin Ingesti</span>
              </Link>
            )}
          </div>

          <div className="user-menu-divider" role="separator" />

          <button
            type="button"
            className="user-menu-item logout-action"
            role="menuitem"
            onClick={handleLogout}
            disabled={isLoggingOut}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>{isLoggingOut ? "Keluar..." : "Keluar (Sign Out)"}</span>
          </button>
        </div>
      )}
    </div>
  );
}
