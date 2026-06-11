"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api-client";
import { resolveAuthErrors, type AuthFormErrors } from "@/lib/auth-errors";
import type { CurrentUser } from "@/lib/auth-types";

export default function LoginPage() {
  return <Suspense fallback={<section className="page-card status-card"><p className="eyebrow">Login</p><h1>Loading sign in</h1></section>}><LoginForm /></Suspense>;
}

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<AuthFormErrors>({});
  const { setCurrentUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

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
      setErrors(resolveAuthErrors(error, "Invalid email or password."));
    } finally { setIsSubmitting(false); }
  }

  return <section className="page-card auth-card"><p className="eyebrow">Login</p><h1>Sign in to RINGKAS</h1><p>Use your email and password to access document search.</p>
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <AuthField label="Email" type="email" value={email} error={errors.email} disabled={isSubmitting} onChange={setEmail} autoComplete="email" />
      <AuthField label="Password" type="password" value={password} error={errors.password} disabled={isSubmitting} onChange={setPassword} autoComplete="current-password" />
      {errors.form ? <p className="form-error">{errors.form}</p> : null}
      <button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? "Signing in..." : "Sign in"}</button>
    </form><p className="page-footnote">Need an account? <Link href="/register">Register</Link></p></section>;
}

function AuthField(props: { label: string; type: string; value: string; error?: string; disabled: boolean; autoComplete: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{props.label}</span><input autoComplete={props.autoComplete} disabled={props.disabled} name={props.label.toLowerCase()} onChange={(event) => props.onChange(event.target.value)} required type={props.type} value={props.value} />{props.error ? <span className="field-error">{props.error}</span> : null}</label>;
}

function resolveSafeRedirectPath(from: string | null, fallback: string) {
  return from?.startsWith("/") && !from.startsWith("//") && !from.includes("://") ? from : fallback;
}
