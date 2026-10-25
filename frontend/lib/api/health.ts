import { apiGet } from "@/lib/api/client";
import type { DatabaseHealthResponse, HealthResponse } from "@/types/api";

/** API-only health check. This endpoint does not query the database. */
export function getApiHealth() {
  return apiGet<HealthResponse>("/health");
}

/**
 * Checks the API and the database in one request (backend: app/api/routes/health.py).
 * Resolves when both are up. Throws ApiError with status 503 when the API is up but the
 * database isn't, or status 0 when the API can't be reached.
 */
export function getDatabaseHealth() {
  return apiGet<DatabaseHealthResponse>("/health/db");
}
