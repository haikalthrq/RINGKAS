export interface ApiRequestOptions extends Omit<RequestInit, "body" | "credentials" | "headers"> {
  headers?: HeadersInit;
  body?: unknown;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly body: unknown;
  readonly rawBody: string;

  constructor(status: number, statusText: string, message: string, body: unknown, rawBody: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.statusText = statusText;
    this.body = body;
    this.rawBody = rawBody;
  }
}

export async function apiRequest<TResponse = unknown>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<TResponse> {
  const headers = new Headers(options.headers);
  let body = options.body;

  if (body !== undefined && !isBodyInit(body)) {
    body = JSON.stringify(body);
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  }

  const response = await fetch(normalizeApiPath(path), {
    ...options,
    body: body as BodyInit | null | undefined,
    credentials: "include",
    headers
  });
  const rawBody = await response.text();
  const parsedBody = parseResponseBody(rawBody, response.headers.get("content-type") ?? "");

  if (!response.ok) {
    const fallbackMessages: Record<number, string> = {
      401: "Authentication is required.",
      403: "You do not have permission to perform this action.",
      429: "Too many requests. Please try again later."
    };
    const problem = typeof parsedBody === "object" && parsedBody !== null
      ? parsedBody as { detail?: unknown; title?: unknown }
      : null;
    const message =
      (typeof problem?.detail === "string" && problem.detail) ||
      (typeof problem?.title === "string" && problem.title) ||
      (typeof parsedBody === "string" && parsedBody.trim()) ||
      fallbackMessages[response.status] ||
      response.statusText ||
      `Request failed with status ${response.status}`;

    throw new ApiClientError(response.status, response.statusText, message, parsedBody, rawBody);
  }

  return parsedBody as TResponse;
}

function normalizeApiPath(path: string): string {
  if (/^https?:\/\//i.test(path)) throw new Error("API calls must use same-origin relative paths.");
  return `/${path.replace(/^\/+/, "")}`;
}

function parseResponseBody(rawBody: string, contentType: string): unknown {
  if (!rawBody) return undefined;
  if (!contentType.includes("json") && !/^[\s]*[\[{\"]/.test(rawBody)) return rawBody;
  try { return JSON.parse(rawBody); } catch { return rawBody; }
}

function isBodyInit(value: unknown): value is BodyInit {
  return typeof value === "string" || value instanceof Blob || value instanceof FormData ||
    value instanceof URLSearchParams || value instanceof ArrayBuffer || ArrayBuffer.isView(value) ||
    (typeof ReadableStream !== "undefined" && value instanceof ReadableStream);
}
