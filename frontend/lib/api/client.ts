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
let onUnauthorized: () => void = () => {};

/**
 * Where requests get the logged-in user's Supabase access token. The Supabase session code
 * registers this once; every request then sends it as "Authorization: Bearer <token>".
 */
export function setAccessTokenGetter(getter: AccessTokenGetter) {
  getAccessToken = getter;
}

/** What to do when the API answers 401 (no valid token). The Supabase session code sends the user to /login. */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

type RequestOptions = {
  /** JSON request body. */
  json?: unknown;
  /** Multipart body, e.g. a file upload. */
  form?: FormData;
  /** Defaults to 5 s; uploads need longer. */
  timeoutMs?: number;
  /** Lets the caller cancel, e.g. a Cancel button. Cancelling rejects with the browser's AbortError. */
  signal?: AbortSignal;
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

/** GETs in flight by path. Several providers (and StrictMode's second effect run) ask for the same data at once. */
const pendingGets = new Map<string, Promise<unknown>>();

/**
 * GET a JSON endpoint, e.g. apiGet<DatabaseHealthResponse>("/health/db"). Identical GETs that overlap
 * share one request; each caller gets its own copy. A caller with its own signal or timeout is never shared.
 */
export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  if (options?.signal || options?.timeoutMs !== undefined) return apiRequest<T>("GET", path, options);
  let pending = pendingGets.get(path);
  if (!pending) {
    pending = apiRequest<T>("GET", path).finally(() => pendingGets.delete(path));
    pendingGets.set(path, pending);
  }
  return pending.then((value) => structuredClone(value) as T);
}

export function apiPost<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("POST", path, options);
}

export function apiPatch<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("PATCH", path, options);
}

export function apiPut<T>(path: string, options?: RequestOptions): Promise<T> {
  return apiRequest<T>("PUT", path, options);
}

/** DELETE an endpoint that answers 204 No Content. */
export async function apiDelete(path: string, options?: RequestOptions): Promise<void> {
  await sendRequest("DELETE", path, options);
}

async function apiRequest<T>(method: string, path: string, options?: RequestOptions): Promise<T> {
  const response = await sendRequest(method, path, options);
  return (await response.json()) as T;
}

/** Send the request with the access token; throw ApiError unless the response is 2xx. */
async function sendRequest(
  method: string,
  path: string,
  { json, form, timeoutMs = DEFAULT_TIMEOUT_MS, signal }: RequestOptions = {},
): Promise<Response> {
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
      signal: withTimeout(timeoutMs, signal),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, `Couldn't reach the API at ${API_BASE_URL}`);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status, `${method} ${path} failed with ${response.status}`, detail);
  }
  return response;
}

function withTimeout(timeoutMs: number, signal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([timeout, signal]) : timeout;
}

/** POST multipart form data. The browser supplies the boundary in Content-Type. */
export function apiPostForm<T>(
  path: string,
  form: FormData,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  return apiRequest<T>("POST", path, { form, timeoutMs });
}

/**
 * POST multipart form data to an NDJSON endpoint and call onLine with each parsed line as it
 * arrives. An exception thrown by onLine stops reading and rejects with that exception.
 */
export async function apiPostFormLines<T>(
  path: string,
  form: FormData,
  onLine: (value: T) => void,
  { timeoutMs = DEFAULT_TIMEOUT_MS, signal }: Pick<RequestOptions, "timeoutMs" | "signal"> = {},
): Promise<void> {
  const response = await sendRequest("POST", path, { form, timeoutMs, signal });
  if (!response.body) throw new ApiError(0, `POST ${path} returned no body`);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffered = "";
  try {
    while (true) {
      let chunk: ReadableStreamReadResult<string>;
      try {
        chunk = await reader.read();
      } catch (error) {
        // Cancelled by the caller, timed out, or the connection dropped mid-stream.
        if (signal?.aborted) throw error;
        throw new ApiError(0, `POST ${path} stopped before it finished`);
      }
      if (chunk.done) break;
      buffered += chunk.value;
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) onLine(JSON.parse(line) as T);
      }
    }
    if (buffered.trim()) onLine(JSON.parse(buffered) as T);
  } finally {
    reader.cancel().catch(() => {});
  }
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
