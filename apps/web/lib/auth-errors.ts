import { ApiClientError } from "./api-client";

export interface AuthFormErrors {
  email?: string;
  password?: string;
  form?: string;
}

export function resolveAuthErrors(error: unknown, fallback: string): AuthFormErrors {
  if (!(error instanceof ApiClientError)) return { form: fallback };

  const record = typeof error.body === "object" && error.body !== null
    ? error.body as { errors?: Record<string, string[]> }
    : {};
  const result: AuthFormErrors = {};

  for (const [key, messages] of Object.entries(record.errors ?? {})) {
    const message = messages.find(Boolean);
    if (key.toLowerCase().includes("email")) result.email = message;
    else if (key.toLowerCase().includes("password")) result.password = message;
    else result.form = message;
  }

  result.form ??= error.message || fallback;
  return result;
}
