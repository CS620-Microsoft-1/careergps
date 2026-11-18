import { z } from "zod";
import { copilotJobFamilySchema, copilotReportIdSchema, copilotSourceSchema, type CopilotResumeContext, type CopilotResponder, type CopilotSource } from "./copilot-types.ts";
import { errorMessage } from "./api/client.ts";

export const MAX_COPILOT_INPUT = 2000;
export const SAMPLE_ANALYSIS_ID = "sample-swe-v1";
export const copilotStorageKey = (owner: string) => `careergps.copilot.continuous.v1:${encodeURIComponent(owner)}`;

type ReplyState = "pending" | "completed" | "failed" | "cancelled" | "interrupted";
export type CopilotMessage = {
  id: string; role: "user" | "assistant"; text: string; createdAt: string;
  analysisId?: string; resumeContext?: CopilotResumeContext; mode?: "foundry_chat"; sources?: CopilotSource[]; replyState?: ReplyState;
};
export type CopilotState = {
  loaded: boolean; open: boolean; conversationId: string | null; createdAt: string | null;
  draft: string; messages: CopilotMessage[]; pendingId: string | null;
  error: string | null; storageWarning: string | null;
  resumeContext: CopilotResumeContext | null; unavailableReason: string | null;
};
type Dependencies = {
  read: () => string | null;
  write: (value: string) => void;
  clear: () => void;
  respond: CopilotResponder;
  id?: () => string;
  now?: () => string;
};
/** Scope all reads, writes and explicit deletion to one account's storage key. */
export function createCopilotStorage(owner: string | null, getStorage: () => Pick<Storage, "getItem" | "setItem" | "removeItem"> = () => localStorage) {
  const key = owner ? copilotStorageKey(owner) : null;
  let lastSaved: string | null = null;
  return {
    read: () => { lastSaved = key ? getStorage().getItem(key) : null; return lastSaved; },
    write: (value: string) => {
      if (!key) return;
      const storage = getStorage();
      // A stale tab must not restore history after another tab has cleared it.
      if (storage.getItem(key) !== lastSaved) throw new Error("History changed in another tab");
      storage.setItem(key, value);
      lastSaved = value;
    },
    clear: () => {
      // Explicitly confirmed deletion can also recover from corrupt saved history.
      if (key) getStorage().removeItem(key);
      lastSaved = null;
    },
  };
}
const INITIAL: CopilotState = {
  loaded: false, open: false, conversationId: null, createdAt: null, draft: "", messages: [],
  pendingId: null, error: null, storageWarning: null, resumeContext: null, unavailableReason: null,
};
const sourceSchema = z.object({ id: z.string().max(200), label: z.string().max(200), excerpt: z.string().max(4000) });
const resumeContextSchema = z.object({
  jobFamily: copilotJobFamilySchema, resumeId: z.uuid().optional(), confirmedAt: z.iso.datetime({ offset: true }).optional(),
  reportId: copilotReportIdSchema.optional(),
});
const messageSchema = z.object({
  id: z.string().min(1).max(100), role: z.enum(["user", "assistant"]), text: z.string().min(1).max(8000),
  createdAt: z.iso.datetime(), analysisId: z.union([z.literal(SAMPLE_ANALYSIS_ID), z.string().regex(/^[0-9a-f]{32}$/)]).optional(),
  resumeContext: resumeContextSchema.optional(), mode: z.literal("foundry_chat").optional(), sources: z.array(sourceSchema).max(10).optional(),
  replyState: z.enum(["pending", "completed", "failed", "cancelled", "interrupted"]).optional(),
}).refine(message => Boolean(message.analysisId) !== Boolean(message.resumeContext)
  && (!message.mode || Boolean(message.resumeContext)));
const storedSchema = z.object({
  version: z.literal(1), open: z.boolean(), conversationId: z.string().min(1).max(100),
  createdAt: z.iso.datetime(), draft: z.string().max(MAX_COPILOT_INPUT), messages: z.array(messageSchema),
});
const chatReplySchema = z.object({ text: z.string().min(1).max(8000), sources: z.array(copilotSourceSchema).max(8), mode: z.literal("foundry_chat") });
const contextKey = (context: CopilotResumeContext | null | undefined) => context
  ? JSON.stringify([context.jobFamily, context.resumeId ?? null, context.confirmedAt ? Date.parse(context.confirmedAt) : null]) : null;
const messageContextKey = (message: CopilotMessage) => {
  const key = contextKey(message.resumeContext) ?? message.analysisId;
  return message.mode ? `${message.mode}:${key}` : key;
};

/** One continuous conversation. Storage and responder are injectable for the backend and offline tests. */
export class CopilotSession {
  private state: CopilotState = INITIAL;
  private listeners = new Set<() => void>();
  private controller: AbortController | null = null;
  private deps: Dependencies;
  private id: () => string;
  private now: () => string;
  private respond: CopilotResponder;

  constructor(deps: Dependencies) {
    this.deps = deps;
    this.id = deps.id ?? (() => crypto.randomUUID());
    this.now = deps.now ?? (() => new Date().toISOString());
    this.respond = deps.respond;
  }
  getSnapshot = () => this.state;
  getServerSnapshot = () => INITIAL;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  initialize = () => {
    if (this.state.loaded) return;
    let storageWarning: string | null = null;
    try {
      const raw = this.deps.read();
      if (raw !== null) {
        const saved = storedSchema.parse(JSON.parse(raw));
        if (new Set(saved.messages.map(m => m.id)).size !== saved.messages.length) throw new Error("Duplicate messages");
        const messages = saved.messages.map(m => m.replyState === "pending" ? { ...m, replyState: "interrupted" as const } : m);
        this.update({ ...saved, messages, loaded: true }, false);
        return;
      }
    } catch {
      storageWarning = "Saved messages could not be loaded. This visit will not overwrite the saved history.";
    }
    this.update({ loaded: true, conversationId: this.id(), createdAt: this.now(), storageWarning }, false);
  };
  private update(patch: Partial<CopilotState>, persist = true) {
    this.state = { ...this.state, ...patch };
    if (persist && this.state.loaded && !this.state.storageWarning) {
      try {
        const { open, conversationId, createdAt, draft, messages } = this.state;
        this.deps.write(JSON.stringify({ version: 1, open, conversationId, createdAt, draft, messages }));
      } catch {
        this.state = { ...this.state, storageWarning: "History could not be saved (storage unavailable, full, or changed in another tab). New messages remain here until you refresh." };
      }
    }
    this.listeners.forEach(listener => listener());
  }
  /** Keep legacy records visible; new chat history stays within its selected context. */
  setResumeContext = (resumeContext: CopilotResumeContext | null, unavailableReason: string | null = null) => {
    const changed = contextKey(resumeContext) !== contextKey(this.state.resumeContext);
    const reportChanged = resumeContext?.reportId !== this.state.resumeContext?.reportId;
    if (changed || reportChanged) this.cancel();
    if (changed || reportChanged || unavailableReason !== this.state.unavailableReason) {
      this.update({ resumeContext, unavailableReason, error: null }, false);
    }
  };
  private currentContextKey = () => {
    const key = contextKey(this.state.resumeContext);
    return key ? `foundry_chat:${key}` : null;
  };
  private completedHistory(message: CopilotMessage) {
    const context = messageContextKey(message);
    const messages = this.state.messages.filter(turn => turn.id !== message.id && messageContextKey(turn) === context);
    const history: { role: "user" | "assistant"; text: string }[] = [];
    for (let index = 0; index < messages.length - 1; index++) {
      const question = messages[index];
      const answer = messages[index + 1];
      if (question.role === "user" && question.replyState === "completed" && answer.role === "assistant") {
        history.push({ role: question.role, text: question.text }, { role: answer.role, text: answer.text });
        index++;
      }
    }
    return history.slice(-20);
  }
  setOpen = (open: boolean) => this.update({ open });
  setDraft = (draft: string) => this.update({ draft: draft.slice(0, MAX_COPILOT_INPUT), error: null });
  /** Called only after UI confirmation. Fail without claiming that saved history was deleted. */
  clear = () => {
    if (!this.state.loaded) return false;
    try {
      this.deps.clear();
    } catch {
      this.update({ error: "Couldn’t clear saved history. Nothing was cleared. Please try again." }, false);
      return false;
    }
    this.controller?.abort();
    this.controller = null;
    this.update({ conversationId: this.id(), createdAt: this.now(), messages: [], draft: "",
      pendingId: null, error: null, storageWarning: null }, false);
    return true;
  };
  send = async (question?: string) => {
    const text = (question ?? this.state.draft).trim();
    if (!this.state.loaded || !text || this.state.pendingId) return;
    if (text.length > MAX_COPILOT_INPUT) {
      this.update({ error: "Please use 2,000 characters or fewer." }, false);
      return;
    }
    if (!this.currentContextKey()) {
      this.update({ error: this.state.unavailableReason ?? "Sign in and select a career direction to use Copilot." }, false);
      return;
    }
    const message: CopilotMessage = { id: this.id(), role: "user", text, createdAt: this.now(),
      resumeContext: this.state.resumeContext!, mode: "foundry_chat", replyState: "pending" };
    this.update({ messages: [...this.state.messages, message], draft: "", error: null });
    await this.run(message.id);
  };
  retry = async () => {
    const last = this.state.messages.at(-1);
    if (!last || last.role !== "user" || !last.replyState || last.replyState === "completed" || this.state.pendingId) return;
    await this.run(last.id);
  };
  private async run(messageId: string) {
    const message = this.state.messages.find(m => m.id === messageId);
    if (!message) return;
    if (messageContextKey(message) !== this.currentContextKey()) {
      this.update({ error: "This question belongs to another résumé or direction. Send a new question for the selected résumé." }, false);
      return;
    }
    const resumeContext = this.state.resumeContext;
    const controller = new AbortController();
    this.controller = controller;
    this.update({ messages: this.state.messages.map(m => m.id === messageId ? { ...m, replyState: "pending" } : m),
      pendingId: messageId, error: null });
    try {
      const rawReply = await this.respond({ question: message.text,
        history: this.completedHistory(message),
        ...(resumeContext ? { jobFamily: resumeContext.jobFamily,
          ...(resumeContext.reportId ? { reportId: resumeContext.reportId } : {}) } : {}) }, controller.signal);
      const reply = chatReplySchema.parse(rawReply);
      if (controller.signal.aborted || this.controller !== controller) return;
      this.controller = null;
      // Conversation scope does not assert that any résumé data was read.
      const identity = { resumeContext: resumeContext!, mode: "foundry_chat" as const };
      this.update({
        messages: [...this.state.messages.map(m => m.id === messageId ? { ...m, ...identity, replyState: "completed" as const } : m),
          { id: this.id(), role: "assistant", createdAt: this.now(), ...identity, text: reply.text, sources: reply.sources }], pendingId: null });
    } catch (error) {
      if (controller.signal.aborted || this.controller !== controller) return;
      this.controller = null;
      this.update({ messages: this.state.messages.map(m => m.id === messageId ? { ...m, replyState: "failed" } : m), pendingId: null,
        error: errorMessage(error, "Copilot could not reply. Please try again.") });
    }
  }
  cancel = () => {
    this.controller?.abort();
    this.controller = null;
    if (!this.state.pendingId) return;
    this.update({ messages: this.state.messages.map(m => m.id === this.state.pendingId ? { ...m, replyState: "cancelled" } : m), pendingId: null });
  };
}
