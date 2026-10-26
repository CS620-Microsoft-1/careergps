"use client";

import { type BackendStatus as Status, useBackendStatus } from "@/components/layout/backend-status-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const DISPLAY: Record<Status, { label: string; dot: string; hint: (apiUrl: string) => string }> = {
  checking: {
    label: "Checking backend…",
    dot: "bg-muted-foreground",
    hint: (apiUrl) => `Contacting the API at ${apiUrl}.`,
  },
  connected: {
    label: "Backend connected",
    dot: "bg-success",
    hint: (apiUrl) => `The API at ${apiUrl} can reach the database.`,
  },
  "database-down": {
    label: "Database unreachable",
    dot: "bg-warning",
    hint: () =>
      "The API is running but can't reach the database. Check DATABASE_URL in backend/.env, or resume the Supabase project.",
  },
  unreachable: {
    label: "Backend unreachable",
    dot: "bg-danger",
    hint: (apiUrl) =>
      `Couldn't reach the API at ${apiUrl}. Start it with "uvicorn app.main:app --reload", then check NEXT_PUBLIC_API_URL and CORS_ORIGINS.`,
  },
};

type BackendStatusProps = {
  className?: string;
  /**
   * Focusable, with a tooltip explaining the state. Pass false inside menus, where an extra tab
   * stop would interfere with the menu's arrow-key navigation.
   */
  interactive?: boolean;
};

/** Colored dot + label showing whether the frontend can reach the API and database. */
export function BackendStatus({ className, interactive = true }: BackendStatusProps) {
  const { status, apiUrl } = useBackendStatus();
  const { label, dot, hint } = DISPLAY[status];

  const badge = (
    <span
      tabIndex={interactive ? 0 : undefined}
      role="status"
      aria-live="polite"
      className={cn(
        "inline-flex min-w-0 items-center gap-2 rounded-lg text-xs font-medium text-ink-2 outline-none focus-visible:ring-2 focus-visible:ring-primary",
        className,
      )}
    >
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full", dot)} />
      <span className="truncate">{label}</span>
    </span>
  );

  if (!interactive) return badge;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent className="max-w-72">{hint(apiUrl)}</TooltipContent>
    </Tooltip>
  );
}
