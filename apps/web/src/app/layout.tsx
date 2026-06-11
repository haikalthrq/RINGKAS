import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/components/auth-provider";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

export const metadata: Metadata = {
  title: "RINGKAS",
  description: "Grounded BPS publication search and question answering"
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="id"><body><AuthProvider><div className="app-shell"><SiteHeader /><main className="page">{children}</main></div></AuthProvider></body></html>;
}
