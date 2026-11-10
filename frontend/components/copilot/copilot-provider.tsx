"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { useAccount } from "@/components/layout/account-provider";
import { CopilotSession, copilotStorageKey, type CopilotState } from "@/lib/copilot-session";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/supabase/config";

const CopilotContext = createContext<{ session: CopilotSession; state: CopilotState; sessionOnly: boolean } | null>(null);

export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const { authUserId, status } = useAccount();
  const owner = authUserId ? `user:${authUserId}` : !SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY ? "local-preview" : null;
  return <OwnerConversation key={owner ?? "unverified"} owner={owner} ready={status === "ready"}>{children}</OwnerConversation>;
}

function OwnerConversation({ owner, ready, children }: { owner: string | null; ready: boolean; children: React.ReactNode }) {
  const [session] = useState(() => {
    const key = owner ? copilotStorageKey(owner) : null;
    let lastSaved: string | null = null;
    return new CopilotSession({
      read: () => { lastSaved = key ? localStorage.getItem(key) : null; return lastSaved; },
      write: (value) => {
        if (!key) return;
        // Do not silently overwrite history written by another open tab.
        if (localStorage.getItem(key) !== lastSaved) throw new Error("History changed in another tab");
        localStorage.setItem(key, value);
        lastSaved = value;
      },
    });
  });
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
