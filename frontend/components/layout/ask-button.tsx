import { Sparkles } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Floating Copilot launcher. Opens the Copilot side panel once it exists. */
export function AskButton() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-disabled
          className="fixed right-[max(1.5rem,env(safe-area-inset-right))] bottom-[max(1.5rem,env(safe-area-inset-bottom))] z-40 flex h-11 items-center gap-2 rounded-full bg-deep px-4.5 text-control font-semibold text-deep-foreground shadow-fab transition-colors outline-none hover:bg-brand-dark focus-visible:ring-3 focus-visible:ring-primary/50"
        >
          <Sparkles aria-hidden className="size-4.5" />
          Ask CareerGPS
        </button>
      </TooltipTrigger>
      <TooltipContent side="left">Coming soon</TooltipContent>
    </Tooltip>
  );
}
