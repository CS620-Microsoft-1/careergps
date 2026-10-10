"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { CopilotPanel } from "@/components/panels/copilot-panel";

type CopilotContextValue = {
  /** Open the Copilot, optionally with a question pre-filled in the message box. */
  openCopilot: (question?: string) => void;
};

const CopilotContext = createContext<CopilotContextValue | null>(null);

/** Owns the Copilot panel so any page or component can open it via useCopilot(). */
export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  // The panel can be opened from anywhere, so remember what to refocus on close.
  const returnFocusRef = useRef<HTMLElement | null>(null);

  const openCopilot = useCallback((question?: string) => {
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    if (question !== undefined) setDraft(question);
    setOpen(true);
  }, []);

  const restoreFocus = useCallback((event: Event) => {
    event.preventDefault();
    returnFocusRef.current?.focus();
  }, []);

  const value = useMemo(() => ({ openCopilot }), [openCopilot]);

  return (
    <CopilotContext value={value}>
      {children}
      <CopilotPanel
        open={open}
        onOpenChange={setOpen}
        onCloseAutoFocus={restoreFocus}
        draft={draft}
        onDraftChange={setDraft}
      />
    </CopilotContext>
  );
}

export function useCopilot() {
  const ctx = useContext(CopilotContext);
  if (!ctx) throw new Error("useCopilot must be used inside <CopilotProvider>");
  return ctx;
}
