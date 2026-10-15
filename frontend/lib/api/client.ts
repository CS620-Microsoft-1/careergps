// Every call to the CareerGPS API goes through this module. Components never call fetch() directly.

/**
 * Where the FastAPI backend runs, from NEXT_PUBLIC_API_URL in .env.local.
 * Written out in full so Next.js can build it into browser code; defaults to the backend's port.
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

const DEFAULT_TIMEOUT_MS = 5000;

type AccessTokenGetter = () => Promise<string | null>;

let getAccessToken: AccessTokenGetter = async () => null;

/**
 * Where requests get the logged-in user's Supabase access token. The Supabase session code
 * registers this once; every request then sends it as "Authorization: Bearer <token>".
 */
export function setAccessTokenGetter(getter: AccessTokenGetter) {
  getAccessToken = getter;
}

type RequestOptions = {
  /** JSON request body. */
  json?: unknown;
  /** Multipart body, e.g. a file upload. */
  form?: FormData;
  /** Defaults to 5 s; uploads need longer. */
  timeoutMs?: number;
};

/** Thrown for any failed API call. */
export class ApiError extends Error {
  /**
   * HTTP status code, or 0 when no response arrived at all: the API isn't running, the request
   * timed out, or the browser blocked it (CORS). Browsers don't tell these apart.
   */
  readonly status: number;
  /** FastAPI's {"detail": "..."} message, when the API sent one. */
  readonly detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** GET a JSON endpoint, e.g. apiGet<DatabaseHealthResponse>("/health/db"). */
export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("GET", path, options);
}

export function apiPost<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("POST", path, options);
}

export function apiPatch<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("PATCH", path, options);
}

async function apiRequest<T>(
  method: string,
  path: string,
  { json, form, timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers = new Headers();
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (json !== undefined) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      // FormData sets its own multipart Content-Type with the boundary.
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new ApiError(0, `Couldn't reach the API at ${API_BASE_URL}`);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(response.status, `${method} ${path} failed with ${response.status}`, detail);
  }

  return (await response.json()) as T;
}

/** POST multipart form data. The browser supplies the boundary in Content-Type. */
export function apiPostForm<T>(
  path: string,
  form: FormData,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  return apiRequest<T>("POST", path, { form, timeoutMs });
}

async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON; there's no detail to show.
  }
  return undefined;
}

/** A message for the user: the API's own explanation for 4xx errors, otherwise a generic one. */
export function errorMessage(error: unknown, fallback = "Something went wrong. Try again.") {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 0) return "Can't reach CareerGPS right now. Check your connection and try again.";
  if (error.status === 401) return "Your session has expired. Log in again.";
  if (error.status >= 400 && error.status < 500 && error.detail) return error.detail;
  return fallback;
}
