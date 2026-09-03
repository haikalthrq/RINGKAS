import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter, Newsreader, JetBrains_Mono } from "next/font/google";
import { AuthProvider } from "@/components/auth-provider";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap"
});

const newsreader = Newsreader({
  subsets: ["latin"],
  variable: "--font-newsreader",
  display: "swap",
  style: ["normal", "italic"]
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap"
});

export const metadata: Metadata = {
  title: {
    default: "RINGKAS — Riset BPS Berbasis Bukti",
    template: "%s | RINGKAS"
  },
  description: "Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik BPS DKI Jakarta",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" }
    ]
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover"
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="id" className={`${inter.variable} ${newsreader.variable} ${jetbrainsMono.variable}`}>
      <body>
        <AuthProvider>
          <div className="app-shell">
            <SiteHeader />
            <main className="page">{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
