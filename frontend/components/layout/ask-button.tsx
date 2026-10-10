"use client";

import { Sparkles } from "lucide-react";

import { useCopilot } from "@/components/panels/copilot-provider";

/** Floating launcher for the Copilot panel. */
export function AskButton() {
  const { openCopilot } = useCopilot();

  return (
    <button
      type="button"
      onClick={() => openCopilot()}
      className="fixed right-[max(1.5rem,env(safe-area-inset-right))] bottom-[max(1.5rem,env(safe-area-inset-bottom))] z-40 flex h-11 items-center gap-2 rounded-full bg-deep px-4.5 text-control font-semibold text-deep-foreground shadow-fab transition-colors outline-none hover:bg-brand-dark focus-visible:ring-3 focus-visible:ring-primary/50"
    >
      <Sparkles aria-hidden className="size-4.5" />
      Ask CareerGPS
    </button>
  );
}
