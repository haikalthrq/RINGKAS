"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { GoogleIcon } from "@/components/google-icon";
import { apiRequest } from "@/lib/api-client";
import { resolveAuthErrors, type AuthFormErrors } from "@/lib/auth-errors";
import type { CurrentUser } from "@/lib/auth-types";

export default function LoginPage() {
  return <Suspense fallback={<section className="page-card status-card"><p className="eyebrow">Masuk</p><h1>Memuat halaman masuk...</h1></section>}><LoginForm /></Suspense>;
}

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<AuthFormErrors>({});
  const { setCurrentUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const googleSignInHref = `/api/auth/google?returnUrl=${encodeURIComponent(resolveSafeRedirectPath(searchParams.get("from"), "/chat"))}`;
  const googleError = getGoogleErrorMessage(searchParams.get("error"), searchParams.get("detail"));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrors({});
    try {
      const user = await apiRequest<CurrentUser>("/api/auth/login", { method: "POST", body: { email, password } });
      setCurrentUser(user);
      router.replace(resolveSafeRedirectPath(searchParams.get("from"), "/chat"));
    } catch (error) {
      setErrors(resolveAuthErrors(error, "Email atau kata sandi tidak sesuai."));
    } finally { setIsSubmitting(false); }
  }

  return (
    <section className="page-card auth-card">
      <p className="eyebrow">Masuk Akun</p>
      <h1>Masuk ke RINGKAS</h1>
      <p className="page-intro">Gunakan akun Anda untuk mengakses riwayat riset dan penelusuran publikasi BPS.</p>
      
      {googleError ? <p className="form-error" role="alert">{googleError}</p> : null}
      
      <a className="google-auth-button" href={googleSignInHref}>
        <GoogleIcon size={18} />
        <span>Lanjutkan dengan Google</span>
      </a>

      <div className="auth-divider" aria-hidden="true">
        <span>atau masuk dengan email</span>
      </div>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <AuthField label="Email" type="email" value={email} error={errors.email} disabled={isSubmitting} onChange={setEmail} autoComplete="email" />
        <AuthField label="Kata Sandi" type="password" value={password} error={errors.password} disabled={isSubmitting} onChange={setPassword} autoComplete="current-password" />
        {errors.form ? <p className="form-error">{errors.form}</p> : null}
        <button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? "Memproses..." : "Masuk"}</button>
      </form>

      <p className="page-footnote">Belum memiliki akun? <Link href="/register">Daftar sekarang</Link></p>
    </section>
  );
}

function getGoogleErrorMessage(error: string | null, detail?: string | null): string | null {
  if (!error) return null;
  switch (error) {
    case "account_exists":
      return "Email Google ini sudah terdaftar dengan kata sandi. Silakan masuk menggunakan kata sandi Anda.";
    case "email_unverified":
      return "Email Google Anda belum terverifikasi oleh Google. Silakan verifikasi akun Google Anda terlebih dahulu.";
    case "account_unavailable":
      return "Akun Anda saat ini tidak dapat diakses atau sedang dibatasi.";
    case "provider_error":
      return detail ? `Google Auth error: ${detail}` : "Gagal menghubungkan akun Google. Pastikan izin akses telah diberikan atau coba lagi.";
    case "login_failed":
      return "Gagal memverifikasi sesi otentikasi Google. Jika menggunakan browser Brave atau ekstensi ad-blocker, pastikan Shields/proteksi cookie dinonaktifkan sementara untuk localhost.";
    case "disabled":
      return "Layanan Google Sign-In belum dikonfigurasi di server (GOOGLE_CLIENT_ID dan GOOGLE_CLIENT_SECRET belum diatur di file .env).";
    default:
      return "Autentikasi Google tidak dapat diselesaikan. Silakan coba lagi atau gunakan formulir kata sandi.";
  }
}

function AuthField(props: { label: string; type: string; value: string; error?: string; disabled: boolean; autoComplete: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{props.label}</span><input autoComplete={props.autoComplete} disabled={props.disabled} name={props.label.toLowerCase()} onChange={(event) => props.onChange(event.target.value)} required type={props.type} value={props.value} />{props.error ? <span className="field-error">{props.error}</span> : null}</label>;
}

function resolveSafeRedirectPath(from: string | null, fallback: string) {
  return from?.startsWith("/") && !from.startsWith("//") && !from.includes("://") ? from : fallback;
}
