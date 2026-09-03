"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { GoogleIcon } from "@/components/google-icon";
import { apiRequest } from "@/lib/api-client";
import { resolveAuthErrors, type AuthFormErrors } from "@/lib/auth-errors";
import type { CurrentUser } from "@/lib/auth-types";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<AuthFormErrors>({});
  const { setCurrentUser } = useAuth();
  const router = useRouter();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;
    setErrors({});
    if (password !== confirmPassword) {
      setErrors({ confirmPassword: "Konfirmasi kata sandi tidak cocok." });
      return;
    }
    setIsSubmitting(true);
    try {
      const user = await apiRequest<CurrentUser>("/api/auth/register", { method: "POST", body: { email, password } });
      setCurrentUser(user);
      router.replace("/chat");
    } catch (error) { setErrors(resolveAuthErrors(error, "Pendaftaran akun gagal. Silakan periksa kembali formulir.")); }
    finally { setIsSubmitting(false); }
  }

  return (
    <section className="page-card auth-card">
      <p className="eyebrow">Daftar Akun</p>
      <h1>Buat Akun Peneliti RINGKAS</h1>
      <p className="page-intro">Daftarkan akun untuk menyimpan sesi riset, pertanyaan, dan sitasi dokumen BPS Anda.</p>

      <a className="google-auth-button" href="/api/auth/google?returnUrl=%2Fchat">
        <GoogleIcon size={18} />
        <span>Daftar dengan Google</span>
      </a>

      <div className="auth-divider" aria-hidden="true">
        <span>atau daftar dengan email</span>
      </div>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label className="field"><span>Email</span><input autoComplete="email" disabled={isSubmitting} name="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />{errors.email ? <span className="field-error">{errors.email}</span> : null}</label>
        <label className="field"><span>Kata Sandi</span><input autoComplete="new-password" disabled={isSubmitting} name="password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />{errors.password ? <span className="field-error">{errors.password}</span> : null}</label>
        <label className="field"><span>Konfirmasi Kata Sandi</span><input aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined} aria-invalid={Boolean(errors.confirmPassword)} autoComplete="new-password" disabled={isSubmitting} name="confirmPassword" onChange={(event) => { setConfirmPassword(event.target.value); setErrors((current) => current.confirmPassword ? { ...current, confirmPassword: undefined } : current); }} required type="password" value={confirmPassword} />{errors.confirmPassword ? <span className="field-error" id="confirm-password-error">{errors.confirmPassword}</span> : null}</label>
        {errors.form ? <p className="form-error">{errors.form}</p> : null}
        <button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? "Mendaftarkan..." : "Daftar Akun"}</button>
      </form>

      <p className="page-footnote">Sudah memiliki akun? <Link href="/login">Masuk sekarang</Link></p>
    </section>
  );
}
