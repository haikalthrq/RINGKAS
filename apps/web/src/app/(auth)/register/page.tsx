"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { apiRequest } from "@/lib/api-client";
import { resolveAuthErrors, type AuthFormErrors } from "@/lib/auth-errors";
import type { CurrentUser } from "@/lib/auth-types";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<AuthFormErrors>({});
  const { setCurrentUser } = useAuth();
  const router = useRouter();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrors({});
    try {
      const user = await apiRequest<CurrentUser>("/api/auth/register", { method: "POST", body: { email, password } });
      setCurrentUser(user);
      router.replace("/documents");
    } catch (error) { setErrors(resolveAuthErrors(error, "Registration failed. Please review the form.")); }
    finally { setIsSubmitting(false); }
  }

  return <section className="page-card auth-card"><p className="eyebrow">Register</p><h1>Create a RINGKAS account</h1><p>Registration signs you in automatically after success.</p>
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <label className="field"><span>Email</span><input autoComplete="email" disabled={isSubmitting} name="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />{errors.email ? <span className="field-error">{errors.email}</span> : null}</label>
      <label className="field"><span>Password</span><input autoComplete="new-password" disabled={isSubmitting} name="password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />{errors.password ? <span className="field-error">{errors.password}</span> : null}</label>
      {errors.form ? <p className="form-error">{errors.form}</p> : null}<button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? "Creating account..." : "Create account"}</button>
    </form><p className="page-footnote">Already have an account? <Link href="/login">Login</Link></p></section>;
}
