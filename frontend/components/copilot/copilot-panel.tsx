"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowLeft, ArrowUp, FileText, LoaderCircle, RotateCcw, Sparkles, Square, X } from "lucide-react";
import { useCopilot } from "@/components/copilot/copilot-provider";
import { Button } from "@/components/ui/button";
import { MAX_COPILOT_INPUT, type CopilotMessage } from "@/lib/copilot-session";
import { LOCAL_COPILOT } from "@/lib/api/copilot";
import { cn } from "@/lib/utils";

const QUESTIONS = ["Why is SQL a gap?", "Which project should I build first?", "I already used SQL. What evidence helps?"];
const STATUS = { failed: "The reply failed. Your message is saved.", cancelled: "Reply stopped.", interrupted: "The previous reply was interrupted. Your message is saved." };

export function CopilotPanel() {
  const { session, state, sessionOnly } = useCopilot();
  const viewport = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const clearButton = useRef<HTMLButtonElement>(null);
  const cancelClearButton = useRef<HTMLButtonElement>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  useEffect(() => {
    if (confirmClear) cancelClearButton.current?.focus();
  }, [confirmClear]);
  function cancelClear() {
    setConfirmClear(false);
    requestAnimationFrame(() => clearButton.current?.focus());
  }
  function clearConversation() {
    const cleared = session.clear();
    setConfirmClear(false);
    if (cleared) {
      setFirstVisible(0);
      followLatest.current = true;
      setShowLatest(false);
      requestAnimationFrame(() => document.getElementById("copilot-input")?.focus());
    } else {
      requestAnimationFrame(() => clearButton.current?.focus());
    }
  }
  const [showLatest, setShowLatest] = useState(false);
  const [firstVisible, setFirstVisible] = useState(() => Math.max(0, state.messages.length - 40));
  const last = state.messages.at(-1);
  const retryable = last?.role === "user" && last.replyState && last.replyState in STATUS;
  function toLatest() {
    const element = viewport.current;
    if (element) element.scrollTop = element.scrollHeight;
    followLatest.current = true;
    setShowLatest(false);
  }
  useEffect(() => {
    const element = viewport.current;
    if (element && followLatest.current) element.scrollTop = element.scrollHeight;
  }, [state.messages, state.pendingId]);
  function submit(question?: string) {
    followLatest.current = true;
    setShowLatest(false);
    void session.send(question);
  }
  function close() {
    session.setOpen(false);
    document.getElementById("copilot-launcher")?.focus();
  }
  return <aside id="copilot-panel" aria-labelledby="copilot-title"
    className="flex h-[min(48rem,90dvh)] min-h-96 min-w-0 scroll-mt-32 flex-col border-t bg-card lg:sticky lg:top-[var(--copilot-nav-height)] lg:h-[calc(100dvh-var(--copilot-nav-height))] lg:min-h-0 lg:border-t-0 lg:border-l">
    <header className="flex shrink-0 items-center gap-3 border-b px-5 py-4">
      <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent"><Sparkles aria-hidden className="size-5" /></span>
      <div className="min-w-0 flex-1"><h2 id="copilot-title" className="text-title">CareerGPS Copilot</h2><p className="text-xs text-muted-foreground">Your next step, together.</p></div>
      <Button variant="ghost" size="icon-sm" onClick={close} aria-label="Close Copilot"><X /></Button>
    </header>
    <div className="shrink-0 border-b bg-background px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs"><span className="font-bold">{LOCAL_COPILOT ? "Sample data · Local demo" : "Sample data · Foundry Agent"}</span><span className="font-mono text-muted-foreground">REPORT V1</span></div>
      <p className="mt-1 text-xs text-muted-foreground">Fictional SWE profile · SQL, deployment & testing.<br />Replies do not use your résumé or the report on the left.</p>
      <button type="button" className="mt-2 flex min-h-9 items-center gap-1 text-xs font-bold underline lg:hidden"
        onClick={() => document.getElementById("career-report")?.focus()}><ArrowLeft aria-hidden className="size-3" />Back to report</button>
    </div>
    {(state.storageWarning || sessionOnly) && <p role="status" className="shrink-0 border-b bg-warning-soft px-5 py-2 text-xs">
      {state.storageWarning ?? "Account unavailable. Messages will last only until you leave or refresh."}
    </p>}
    <div ref={viewport} role="region" aria-label="Conversation history" tabIndex={0}
      onScroll={() => {
        const element = viewport.current;
        if (!element) return;
        const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
        followLatest.current = nearBottom;
        setShowLatest(!nearBottom);
      }} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5">
      {firstVisible > 0 && <Button variant="secondary" size="sm" className="mb-5 w-full" onClick={() => {
        const element = viewport.current;
        const height = element?.scrollHeight ?? 0;
        const top = element?.scrollTop ?? 0;
        followLatest.current = false;
        setFirstVisible(index => Math.max(0, index - 40));
        requestAnimationFrame(() => { if (element) element.scrollTop = top + element.scrollHeight - height; });
      }}>Load earlier messages ({firstVisible})</Button>}
      {!state.messages.length && <div className="pb-5 pt-3">
        <p className="eyebrow">A little clarity goes a long way</p>
        <h3 className="mt-3 text-section">Let’s work through<br />your next step.</h3>
        <p className="mt-3 text-sm/6 text-muted-foreground">Explore a sample skill gap, find evidence, or turn an idea into a small project.</p>
        <div className="mt-5 grid gap-2">{QUESTIONS.map(question => <button key={question} type="button" onClick={() => submit(question)}
          className="flex min-h-11 items-center justify-between gap-3 rounded-xl border bg-background px-3 py-3 text-left text-sm hover:border-foreground">
          {question}<ArrowUp aria-hidden className="size-4 shrink-0 rotate-45" />
        </button>)}</div>
        <p className="mt-5 text-xs/5 text-muted-foreground">One ongoing conversation. Come back anytime to continue where you left off.</p>
      </div>}
      <div className="space-y-5">{state.messages.slice(firstVisible).map(message => <Message key={message.id} message={message} />)}</div>
      {state.pendingId && <p role="status" className="mt-5 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle aria-hidden className="size-4 animate-spin" />{LOCAL_COPILOT ? "Preparing sample reply…" : "Working on your question…"}</p>}
      {retryable && <div role="status" className="mt-4 rounded-xl bg-secondary p-3 text-sm">
        <p>{STATUS[last.replyState as keyof typeof STATUS]}</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => void session.retry()}>Retry reply</Button>
      </div>}
    </div>
    <div role="status" aria-live="polite" className="sr-only">{last?.role === "assistant" && !state.pendingId ? `Copilot: ${last.text}` : ""}</div>
    {showLatest && <button type="button" onClick={toLatest} className="mx-auto mb-2 flex min-h-9 shrink-0 items-center gap-1 rounded-full border bg-background px-3 text-xs font-bold"><ArrowDown aria-hidden className="size-3" />Latest messages</button>}
    <footer className="shrink-0 border-t p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      {state.error && <p role="alert" className="mb-2 text-sm text-danger">{state.error}</p>}
      <form onSubmit={event => { event.preventDefault(); submit(); }} className="rounded-2xl border border-line-strong bg-background p-3 focus-within:ring-2 focus-within:ring-ring/20">
        <label htmlFor="copilot-input" className="sr-only">Message CareerGPS Copilot</label>
        <textarea id="copilot-input" rows={2} maxLength={MAX_COPILOT_INPUT} value={state.draft}
          placeholder="Ask about a gap or your next step…" onChange={event => session.setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              if (!state.pendingId) submit();
            }
          }} className="block max-h-36 min-h-12 w-full resize-y border-0 bg-transparent text-sm/6 outline-none placeholder:text-muted-foreground"
          aria-describedby="copilot-input-hint" />
        <div className="mt-1 flex items-center justify-between gap-2">
          <span id="copilot-input-hint" className="text-[0.6875rem] text-muted-foreground">{state.draft.length > 1800 ? `${state.draft.length} / ${MAX_COPILOT_INPUT}` : "Enter to send · Shift + Enter for a new line"}</span>
          {state.pendingId ? <Button type="button" size="icon-sm" onClick={session.cancel} aria-label="Stop reply"><Square className="size-3.5" /></Button>
            : <Button type="submit" size="icon-sm" disabled={!state.loaded || !state.draft.trim()} aria-label="Send message"><ArrowUp /></Button>}
        </div>
      </form>
      <p className="mt-2 text-center text-[0.6875rem] text-muted-foreground">{state.storageWarning || sessionOnly ? "History is not being saved" : "History saved in this browser"} · {LOCAL_COPILOT ? "Scripted replies" : "AI replies may be inaccurate"}</p>
      <div className="mt-2 flex justify-center">
        <Button ref={clearButton} type="button" variant="ghost" size="sm"
          disabled={!state.loaded || confirmClear || (!state.messages.length && !state.draft && !state.storageWarning)}
          onClick={() => setConfirmClear(true)}><RotateCcw aria-hidden />Clear and restart</Button>
      </div>
      {confirmClear && <div role="alertdialog" aria-labelledby="copilot-clear-title" aria-describedby="copilot-clear-description"
        className="mt-2 rounded-xl border bg-background p-3" onKeyDown={event => {
          if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); cancelClear(); }
        }}>
        <h3 id="copilot-clear-title" className="text-sm font-bold">Clear this conversation?</h3>
        <p id="copilot-clear-description" className="mt-1 text-xs/5 text-muted-foreground">This will permanently delete this account’s messages and draft from this browser and stop any pending reply.</p>
        <div className="mt-3 flex justify-end gap-2">
          <Button ref={cancelClearButton} type="button" variant="outline" size="sm" onClick={cancelClear}>Cancel</Button>
          <Button type="button" variant="destructive" size="sm" onClick={clearConversation}>Confirm clear</Button>
        </div>
      </div>}
    </footer>
  </aside>;
}

function Message({ message }: { message: CopilotMessage }) {
  const user = message.role === "user";
  return <article aria-label={user ? "Your message" : "Copilot sample reply"} className={cn("min-w-0", user && "ml-7")}>
    <p className="mb-1.5 flex items-center gap-1.5 text-xs font-bold">{!user && <Sparkles aria-hidden className="size-3.5" />}{user ? "You" : "Copilot · Sample reply"}</p>
    <div className={cn("rounded-2xl p-3.5", user ? "rounded-tr-sm bg-deep text-deep-foreground" : "rounded-tl-sm border bg-background")}>
      <p className="text-sm/6 whitespace-pre-wrap [overflow-wrap:anywhere]">{message.text}</p>
      {!!message.sources?.length && <details className="mt-3 border-t pt-3">
        <summary className="cursor-pointer text-xs font-bold">Sample evidence ({message.sources.length})</summary>
        <ul className="mt-3 grid gap-3">{message.sources.map(source => <li key={source.id} className="text-xs/5 [overflow-wrap:anywhere]">
          <p className="flex items-center gap-1 font-bold"><FileText aria-hidden className="size-3 shrink-0" />{source.label}</p>
          <p className="mt-1 text-muted-foreground">{source.excerpt}</p>
        </li>)}</ul>
      </details>}
    </div>
    <time dateTime={message.createdAt} className="mt-1 block text-[0.6875rem] text-muted-foreground">{new Date(message.createdAt).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
  </article>;
}
