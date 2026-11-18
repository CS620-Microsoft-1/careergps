"use client";

import { Fragment, createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { getMe, updateAccount } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";
import { AccountSession, type AccountState } from "@/lib/account-session";
import { ApiError, clearPendingApiGets } from "@/lib/api/client";
import type { User } from "@/types/api";

type Changes = Parameters<typeof updateAccount>[0];
type AccountContextValue = AccountState<User> & {
  initials: string;
  displayName: string;
  /** PATCH /me, then keep the new row. */
  update: (changes: Parameters<typeof updateAccount>[0]) => Promise<User>;
};

const AccountContext = createContext<AccountContextValue | null>(null);

/** The signed-in student, shared by the nav bar and the pages. Works from Supabase alone if the API is down. */
export function AccountProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AccountState<User>>({ status: "loading", email: null, authUserId: null, user: null });
  const session = useRef<AccountSession<User, Changes> | null>(null);

  useEffect(() => {
    const controller = new AccountSession<User, Changes>({
      currentUser: async () => (await getSupabase().auth.getUser()).data.user,
      subscribe: changed => {
        try {
          const { data } = getSupabase().auth.onAuthStateChange((_event, auth) => changed(auth?.user ?? null));
          return () => data.subscription.unsubscribe();
        } catch { return () => {}; }
      },
      loadProfile: async owner => (await getMe(owner)).user,
      updateProfile: (changes, owner) => updateAccount(changes, owner),
      publish: setState,
      ownerChanged: clearPendingApiGets,
    });
    session.current = controller;
    controller.start();
    return () => {
      session.current = null;
      controller.stop();
    };
  }, []);

  const update = useCallback(async (changes: Parameters<typeof updateAccount>[0]) => {
    if (!session.current || !state.authUserId) throw new ApiError(409, "Account unavailable", "Sign in before updating your account.");
    return session.current.update(changes, state.authUserId);
  }, [state.authUserId]);

  const name = state.user ? `${state.user.first_name} ${state.user.last_name}`.trim() : "";
  const displayName = name || state.email?.split("@")[0] || "";
  return (
    <AccountContext value={{ ...state, update, displayName, initials: initialsOf(displayName || "S") }}>
      <Fragment key={state.authUserId ?? "signed-out"}>{children}</Fragment>
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
