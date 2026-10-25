"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { getMarketDemand } from "@/lib/api/market";
import type { JobFamily, MarketDemandSnapshot } from "@/types/api";

type MarketState = { family: JobFamily | null; data: MarketDemandSnapshot | null; loading: boolean; error?: string };

export function useMarketDemand(family: JobFamily | null) {
  const [state, setState] = useState<MarketState>({ family: null, data: null, loading: false });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let active = true;
    if (!family) return;
    // Defer to the effect's async work, and never show data for a previous role.
    void Promise.resolve().then(async () => {
      if (!active) return;
      setState({ family, data: null, loading: true });
      try {
        const data = await getMarketDemand(family, revision > 0);
        if (active) setState({ family, data, loading: false });
      } catch (error) {
        if (active) setState({ family, data: null, loading: false,
          error: error instanceof ApiError ? error.detail ?? error.message
            : error instanceof Error ? error.message : "Market demand could not be loaded." });
      }
    });
    return () => { active = false; };
  }, [family, revision]);
  if (!family) return { data: null, loading: false, error: undefined, reload };
  return { data: state.family === family ? state.data : null,
    loading: state.family !== family || state.loading,
    error: state.family === family ? state.error : undefined, reload };
}
