import Link from "next/link";

import { SignOutLink } from "@/components/auth/sign-out-link";
import { cn } from "@/lib/utils";

/** Header for the setup pages: the wordmark only, so nothing pulls students out of setup. */
export function SetupHeader() {
  return (
    <header className="border-b border-border bg-card pt-[env(safe-area-inset-top)]">
      <div className="mx-auto flex max-w-300 items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link href="/dashboard" className="rounded-md text-[1.375rem] leading-8 font-extrabold tracking-[-0.01em]">CareerGPS</Link>
        <SignOutLink />
      </div>
    </header>
  );
}

export const SETUP_STEPS = ["Résumé", "Your info", "Target role"] as const;

/** One bar per step: done steps black, the current one lime. */
export function SetupStepper({ current, steps = SETUP_STEPS, label = "Setup steps", className }: {
  current: number; steps?: readonly string[]; label?: string; className?: string;
}) {
  return (
    <ol aria-label={label} className={cn("grid grid-cols-3 gap-2", className)}>
      {steps.map((label, index) => (
        <li key={label} aria-current={index === current ? "step" : undefined} className="grid gap-2">
          <span aria-hidden className={cn("h-1.5 rounded-full",
            index < current ? "bg-foreground" : index === current ? "bg-accent ring-1 ring-foreground/40" : "bg-border")} />
          <span className={cn("eyebrow truncate", index === current && "text-foreground")}>
            {index + 1} · {label}
            <span className="sr-only">{index < current ? ", done" : index === current ? ", current step" : ""}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
