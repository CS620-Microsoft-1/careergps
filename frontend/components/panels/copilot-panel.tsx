"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  COPILOT_QUESTIONS, DEMO_ANALYSIS_ID, respondToCopilot,
  type CopilotResponder, type CopilotReply, type CopilotTurn,
} from "@/lib/api/copilot";

type Message = CopilotTurn & { id: number; sources?: CopilotReply["sources"] };
type CopilotPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus: (event: Event) => void;
  draft: string;
  onDraftChange: (draft: string) => void;
  /** Async boundary for the future backend and interaction tests. */
  respond?: CopilotResponder;
};

export function CopilotPanel({
  open, onOpenChange, onCloseAutoFocus, draft, onDraftChange, respond = respondToCopilot,
}: CopilotPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const nextId = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, pending, open]);

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy.current) return;
    busy.current = true;
    setPending(true);
    setError(null);
    const history = [...messages, { id: nextId.current++, role: "user" as const, text: trimmed }];
    setMessages(history);
    onDraftChange("");
    try {
      const reply = await respond({
        question: trimmed,
        history: messages.map(({ role, text }) => ({ role, text })),
        analysisId: DEMO_ANALYSIS_ID,
      });
      setMessages([...history, { id: nextId.current++, role: "assistant", ...reply }]);
    } catch {
      setError("Couldn't get a response. Your question is back in the message box; try again.");
      setMessages(messages);
      onDraftChange(trimmed);
    } finally {
      busy.current = false;
      setPending(false);
      inputRef.current?.focus();
    }
  }

  function reset() {
    if (busy.current) return;
    setMessages([]);
    setError(null);
    onDraftChange("");
    inputRef.current?.focus();
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        onCloseAutoFocus={onCloseAutoFocus}
        className="min-h-0 pb-[env(safe-area-inset-bottom)] sm:data-[side=right]:inset-y-auto sm:data-[side=right]:right-6 sm:data-[side=right]:bottom-6 sm:data-[side=right]:h-[min(42rem,calc(100dvh-3rem))] sm:data-[side=right]:max-w-105 sm:rounded-2xl sm:border"
      >
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2"><Sparkles aria-hidden className="size-4 text-primary" /> CareerGPS Copilot</SheetTitle>
          <SheetDescription className="text-xs">Understand your gaps. Choose your next step.</SheetDescription>
        </SheetHeader>
        <div className="border-b bg-warning-soft px-5 py-3 text-xs text-foreground">
          <p className="font-semibold">Prototype · Sample data</p>
          <p className="mt-1 text-ink-2">Scripted responses for a sample SWE profile. No AI or personal analysis is connected.</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5">
          <div className="mb-4 rounded-xl border bg-background p-3 text-control">
            <p className="font-semibold">Sample context</p>
            <p className="mt-1 text-ink-2">Target: Software Engineer · Skill under review: SQL</p>
          </div>
          {messages.length === 0 && (
            <div className="mb-5 space-y-2">
              <h2 className="text-title">Let’s make sense of your results</h2>
              <p className="text-control text-ink-2">Explore why SQL was flagged, where to start, or how to show experience you already have.</p>
            </div>
          )}
          <div role="log" aria-label="CareerGPS conversation" aria-live="polite" aria-relevant="additions" className="space-y-4">
            {messages.map((message) => (
              <div key={message.id} className={message.role === "user" ? "ml-6 rounded-xl bg-deep p-3 text-deep-foreground" : "mr-2 rounded-xl border bg-card p-3"}>
                <p className="mb-1 text-xs font-semibold">{message.role === "user" ? "You" : "CareerGPS · Sample response"}</p>
                <p className="whitespace-pre-wrap break-words text-control">{message.text}</p>
                {!!message.sources?.length && (
                  <details className="mt-3 border-t pt-2 text-xs">
                    <summary className="cursor-pointer font-semibold text-primary">View sample evidence ({message.sources.length})</summary>
                    <ul className="mt-2 space-y-3">
                      {message.sources.map((source) => <li key={source.label}><p className="font-medium">{source.label}</p><p className="mt-1 text-ink-2">{source.excerpt}</p></li>)}
                    </ul>
                  </details>
                )}
              </div>
            ))}
          </div>
          {pending && <p role="status" className="mt-4 flex items-center gap-2 text-control text-muted-foreground"><LoaderCircle aria-hidden className="size-4 animate-spin" /> Preparing sample response…</p>}
          {error && <p role="alert" className="mt-4 rounded-lg bg-danger-soft p-3 text-control text-danger">{error}</p>}
          <div className="mt-5 grid gap-2">
            <p className="text-xs font-medium text-muted-foreground">Try a question</p>
            {COPILOT_QUESTIONS.map((question) => (
              <button key={question} type="button" disabled={pending} onClick={() => void send(question)} className="min-h-9 rounded-lg border bg-card px-3 py-2 text-left text-control transition-colors enabled:hover:border-primary enabled:hover:bg-accent disabled:opacity-50">{question}</button>
            ))}
          </div>
          <div ref={endRef} />
        </div>
        <SheetFooter className="flex-col">
          <form className="flex w-full gap-2" onSubmit={(event) => { event.preventDefault(); void send(draft); }}>
            <Input ref={inputRef} aria-label="Ask CareerGPS" placeholder="Ask about the sample SQL gap…" value={draft} maxLength={2000} onChange={(event) => onDraftChange(event.target.value)} readOnly={pending} className="min-w-0 flex-1" />
            <Button type="submit" size="icon" disabled={pending || !draft.trim()} aria-label="Send message"><ArrowUp aria-hidden className="size-4" /></Button>
          </form>
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>Demo only · Conversation clears on refresh</span>
            <button type="button" onClick={reset} disabled={pending || !messages.length} className="flex min-h-9 shrink-0 items-center gap-1 rounded px-1 enabled:hover:text-primary disabled:opacity-50"><RotateCcw aria-hidden className="size-3" /> Reset</button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
