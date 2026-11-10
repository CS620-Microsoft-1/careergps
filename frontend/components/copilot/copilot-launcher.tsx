"use client";

import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCopilot } from "@/components/copilot/copilot-provider";

export function CopilotLauncher() {
  const { session, state } = useCopilot();
  return <Button id="copilot-launcher" variant={state.open ? "accent" : "outline"} size="icon-sm"
    className="sm:w-auto sm:gap-1.5 sm:px-3.5" aria-label="Copilot"
    disabled={!state.loaded} aria-expanded={state.open} aria-controls="copilot-panel"
    onClick={() => {
      session.setOpen(!state.open);
      if (!state.open) requestAnimationFrame(() => document.getElementById("copilot-input")?.focus());
    }}>
    <Sparkles aria-hidden /><span className="hidden sm:inline">Copilot</span>
  </Button>;
}
