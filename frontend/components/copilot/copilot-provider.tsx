"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { useAccount } from "@/components/layout/account-provider";
import { CopilotSession, createCopilotStorage, type CopilotState } from "@/lib/copilot-session";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

import { LOCAL_COPILOT, respondToCopilot } from "@/lib/api/copilot";
import { respondToMockCopilot } from "@/lib/copilot-mock";

const CopilotContext = createContext<{ session: CopilotSession; state: CopilotState; sessionOnly: boolean } | null>(null);

export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const { authUserId, status } = useAccount();
  const owner = authUserId ? `user:${authUserId}` : !SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY ? "local-preview" : null;
  return <OwnerConversation key={owner ?? "unverified"} owner={owner} ready={status === "ready"}>{children}</OwnerConversation>;
}

function OwnerConversation({ owner, ready, children }: { owner: string | null; ready: boolean; children: React.ReactNode }) {
  const [session] = useState(() => new CopilotSession({ ...createCopilotStorage(owner), respond: LOCAL_COPILOT ? respondToMockCopilot : respondToCopilot }));
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getServerSnapshot);
  useEffect(() => {
    if (ready) session.initialize();
    return () => session.cancel();
  }, [session, ready]);
  return <CopilotContext value={{ session, state, sessionOnly: !owner }}>{children}</CopilotContext>;
}

export function useCopilot() {
  const value = useContext(CopilotContext);
  if (!value) throw new Error("useCopilot must be inside CopilotProvider");
  return value;
}
