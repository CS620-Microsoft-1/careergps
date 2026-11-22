"use client";

import { useId, useState } from "react";
import { LoaderCircle, Trash2 } from "lucide-react";

import { useAccount } from "@/components/layout/account-provider";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/client";
import { deleteAccount } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";

const DELETED = ["Your account and login", "Every résumé version you confirmed", "Your destinations and skill-gap results",
  "Your action plan and saved courses"];

/** True when the typed text is the account's email, ignoring case and surrounding spaces. */
export function confirmsEmail(typed: string, email: string | null): boolean {
  return Boolean(email) && typed.trim().toLowerCase() === email!.trim().toLowerCase();
}

/** Profile card that permanently deletes the account after the student types their email. */
export function DeleteAccount() {
  const { email } = useAccount();
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const confirmed = confirmsEmail(typed, email);

  const changeOpen = (next: boolean) => {
    if (pending) return; // The request can't be recalled; keep the dialog until it answers.
    setOpen(next);
    if (!next) {
      setTyped("");
      setError(undefined);
    }
  };

  const confirm = async () => {
    if (!confirmed || pending) return;
    setPending(true);
    setError(undefined);
    try {
      await deleteAccount();
    } catch (failure) {
      // 503: deletion isn't configured on the server, so retrying won't help.
      setError(failure instanceof ApiError && failure.status === 503
        ? "Account deletion isn't available right now. Try again later or contact support."
        : errorMessage(failure, "We couldn't delete your account. Try again."));
      setPending(false);
      return;
    }
    // The account is gone: drop this browser's session, then a full page load so no state survives.
    await getSupabase().auth.signOut({ scope: "local" }).catch(() => {});
    window.location.replace("/login?deleted=1");
  };

  return (
    <section aria-labelledby="delete-account" className="rounded-2xl border border-destructive/20 bg-destructive/10 p-6">
      <h2 id="delete-account" className="text-title">Delete account</h2>
      <p className="mt-2 text-sm/6 text-muted-foreground">
        Permanently removes your account, résumés, destinations, skill-gap results, plan and courses. This can’t be undone.
      </p>
      <AlertDialog open={open} onOpenChange={changeOpen}>
        <AlertDialogTrigger asChild>
          <Button variant="outline" disabled={!email}
            className="mt-4 border-destructive/40 bg-card text-destructive hover:bg-card hover:text-destructive hover:border-destructive">
            <Trash2 data-icon="inline-start" />Delete account…
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent
          onEscapeKeyDown={(event) => { if (pending) event.preventDefault(); }}
          className="gap-5 rounded-2xl p-6 data-[size=default]:max-w-[calc(100%-2rem)] data-[size=default]:sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-title font-bold">Delete your account?</AlertDialogTitle>
            <AlertDialogDescription className="text-left">
              This permanently deletes everything below. It can’t be undone, and you’d have to sign up again to use CareerGPS.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="grid list-disc gap-1 pl-5 text-sm/6">
            {DELETED.map((item) => <li key={item}>{item}</li>)}
          </ul>
          <div className="grid min-w-0 gap-2">
            <label htmlFor={inputId} className="text-sm font-semibold">
              Type <span className="font-mono break-all">{email}</span> to confirm
            </label>
            <Input id={inputId} type="email" autoComplete="off" spellCheck={false} value={typed} disabled={pending}
              onChange={(event) => setTyped(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void confirm(); }} />
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <AlertDialogFooter className="-mx-6 -mb-6 rounded-b-2xl px-6 py-4">
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <Button disabled={!confirmed || pending} onClick={() => void confirm()}
              className="bg-destructive text-white hover:bg-[color-mix(in_oklch,var(--destructive),black_15%)]">
              {pending && <LoaderCircle data-icon="inline-start" className="motion-safe:animate-spin" />}
              {pending ? "Deleting…" : "Delete account"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
