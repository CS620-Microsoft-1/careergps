import { apiGet } from "@/lib/api/client";
import type { JobFamily, MarketDemandSnapshot } from "@/types/api";

const cached = new Map<JobFamily, MarketDemandSnapshot>();
const requests = new Map<JobFamily, Promise<MarketDemandSnapshot>>();

/** A role-specific local snapshot, independent of any résumé/model request. */
export function getMarketDemand(family: JobFamily, refresh = false): Promise<MarketDemandSnapshot> {
  const existing = requests.get(family);
  if (existing) return existing;
  const saved = cached.get(family);
  if (saved && !refresh) return Promise.resolve(saved);
  const request = apiGet<MarketDemandSnapshot>(`/skill-gaps/market/${encodeURIComponent(family)}`)
    .then((data) => {
      if (data.job_family !== family) throw new Error("The market snapshot does not match the selected role.");
      cached.set(family, data);
      return data;
    }).finally(() => { requests.delete(family); });
  requests.set(family, request);
  return request;
}
