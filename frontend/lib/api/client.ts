// Every call to the CareerGPS API goes through this module. Components never call fetch() directly.

/**
 * Where the FastAPI backend runs, from NEXT_PUBLIC_API_URL in .env.local.
 * Written out in full so Next.js can build it into browser code; defaults to the backend's port.
 */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export const IS_LOCAL_MODE = process.env.NEXT_PUBLIC_LOCAL_MODE === "true";

const TIMEOUT_MS = 5000;

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
export async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(0, `Couldn't reach the API at ${API_BASE_URL}`);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(response.status, `GET ${path} failed with ${response.status}`, detail);
  }

  return (await response.json()) as T;
}

/** POST multipart form data. The browser supplies the boundary in Content-Type. */
export async function apiPostForm<T>(
  path: string,
  form: FormData,
  timeoutMs = TIMEOUT_MS,
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new ApiError(0, `Couldn't reach the API at ${API_BASE_URL}`);
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(response.status, `POST ${path} failed with ${response.status}`, detail);
  }

  return (await response.json()) as T;
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

/** Submit JSON; long work is queued by the API and then polled separately. */
export async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new ApiError(0, "The request could not be confirmed. Try again; an existing matching analysis will be reused.");
  }
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(response.status, `POST ${path} failed with ${response.status}`, detail);
  }
  return (await response.json()) as T;
}
