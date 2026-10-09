"use client";

import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

// Shown as examples of what the Copilot will answer; inactive until analysis exists.
const EXAMPLE_QUESTIONS = [
  "What should I focus on this semester?",
  "Why do I have this skill gap?",
  "What jobs am I currently competitive for?",
  "What project would improve my profile the most?",
  "Which UW–Madison courses could help me?",
];

type CopilotPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where focus goes when the panel closes (it has no built-in trigger). */
  onCloseAutoFocus: (event: Event) => void;
  draft: string;
  onDraftChange: (draft: string) => void;
};

/**
 * Single place for questions, explanations and sources. Shell only: answers,
 * citations and the agent trace arrive once the backend Copilot API exists.
 */
export function CopilotPanel({
  open,
  onOpenChange,
  onCloseAutoFocus,
  draft,
  onDraftChange,
}: CopilotPanelProps) {
  // No backend yet, so the conversation can't start.
  const available = false;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        onCloseAutoFocus={onCloseAutoFocus}
        className="pb-[env(safe-area-inset-bottom)]"
      >
        <SheetHeader>
          <SheetTitle>CareerGPS Copilot</SheetTitle>
          <SheetDescription className="text-xs">
            Answers backed by your analysis and its sources
          </SheetDescription>
        </SheetHeader>

        <div className="grid flex-1 content-start gap-2.5 overflow-y-auto p-5">
          <div className="mb-2 grid justify-items-center gap-1 py-4 text-center">
            <span className="mb-2 grid size-10 place-items-center rounded-full bg-accent text-primary">
              <Sparkles aria-hidden className="size-5" />
            </span>
            <p className="font-semibold">Ask about your career path</p>
            <p className="max-w-72 text-control text-muted-foreground">
              After your first analysis, ask about your gaps, jobs, projects or courses. Every
              answer shows its sources and how it was worked out.
            </p>
          </div>
          <p className="text-xs font-medium text-muted-foreground">Example questions</p>
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              disabled={!available}
              onClick={() => onDraftChange(q)}
              className="rounded-lg border bg-card px-3 py-2.5 text-left text-control transition-colors enabled:hover:border-primary enabled:hover:text-primary disabled:text-muted-foreground"
            >
              {q}
            </button>
          ))}
        </div>

        <SheetFooter>
          <form
            className="flex w-full gap-2"
            onSubmit={(e) => e.preventDefault()}
          >
            <Input
              aria-label="Ask CareerGPS"
              placeholder={available ? "Ask CareerGPS…" : "Available after your first analysis"}
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              disabled={!available}
              className="h-9"
            />
            <Button type="submit" disabled={!available || !draft.trim()}>
              Send
            </Button>
          </form>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
