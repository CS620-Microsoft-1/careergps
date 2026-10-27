"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { getMe, updateAccount } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";
import type { User } from "@/types/api";

type AccountState = { status: "loading" | "ready"; email: string | null; user: User | null };
type AccountContextValue = AccountState & {
  initials: string;
  displayName: string;
  /** PATCH /me, then keep the new row. */
  update: (changes: Parameters<typeof updateAccount>[0]) => Promise<User>;
};

const AccountContext = createContext<AccountContextValue | null>(null);

/** The signed-in student, shared by the nav bar and the pages. Works from Supabase alone if the API is down. */
export function AccountProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AccountState>({ status: "loading", email: null, user: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let email: string | null = null;
      let user: User | null = null;
      try {
        const { data } = await getSupabase().auth.getUser();
        email = data.user?.email ?? null;
        if (data.user) user = (await getMe().catch(() => null))?.user ?? null;
      } catch {
        // Supabase isn't configured (UI-only development).
      }
      if (!cancelled) setState({ status: "ready", email, user });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback(async (changes: Parameters<typeof updateAccount>[0]) => {
    const user = await updateAccount(changes);
    setState((current) => ({ ...current, user }));
    return user;
  }, []);

  const name = state.user ? `${state.user.first_name} ${state.user.last_name}`.trim() : "";
  const displayName = name || state.email?.split("@")[0] || "";
  return (
    <AccountContext value={{ ...state, update, displayName, initials: initialsOf(displayName || "S") }}>
      {children}
    </AccountContext>
  );
}

export function useAccount() {
  const value = useContext(AccountContext);
  if (!value) throw new Error("useAccount must be inside AccountProvider");
  return value;
}

export function initialsOf(name: string) {
  // Whitespace only, so an email-derived name like "avery.chen" gives "A".
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? "S")[0];
  return letters.toUpperCase();
}
