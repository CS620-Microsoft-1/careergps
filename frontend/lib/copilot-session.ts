import { z } from "zod";
import { respondToMockCopilot } from "./copilot-mock.ts";
import type { CopilotResponder, CopilotSource } from "./copilot-types.ts";
import { errorMessage } from "./api/client.ts";

export const MAX_COPILOT_INPUT = 2000;
export const SAMPLE_ANALYSIS_ID = "sample-swe-v1";
export const copilotStorageKey = (owner: string) => `careergps.copilot.continuous.v1:${encodeURIComponent(owner)}`;

type ReplyState = "pending" | "completed" | "failed" | "cancelled" | "interrupted";
export type CopilotMessage = {
  id: string; role: "user" | "assistant"; text: string; createdAt: string;
  analysisId: typeof SAMPLE_ANALYSIS_ID; sources?: CopilotSource[]; replyState?: ReplyState;
};
export type CopilotState = {
  loaded: boolean; open: boolean; conversationId: string | null; createdAt: string | null;
  draft: string; messages: CopilotMessage[]; pendingId: string | null;
  error: string | null; storageWarning: string | null;
};
type Dependencies = {
  read: () => string | null;
  write: (value: string) => void;
  clear: () => void;
  respond?: CopilotResponder;
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
  pendingId: null, error: null, storageWarning: null,
};
const sourceSchema = z.object({ id: z.string().max(200), label: z.string().max(200), excerpt: z.string().max(4000) });
const messageSchema = z.object({
  id: z.string().min(1).max(100), role: z.enum(["user", "assistant"]), text: z.string().min(1).max(8000),
  createdAt: z.iso.datetime(), analysisId: z.literal(SAMPLE_ANALYSIS_ID), sources: z.array(sourceSchema).max(10).optional(),
  replyState: z.enum(["pending", "completed", "failed", "cancelled", "interrupted"]).optional(),
});
const storedSchema = z.object({
  version: z.literal(1), open: z.boolean(), conversationId: z.string().min(1).max(100),
  createdAt: z.iso.datetime(), draft: z.string().max(MAX_COPILOT_INPUT), messages: z.array(messageSchema),
});
const replySchema = z.object({ text: z.string().min(1).max(8000), sources: z.array(sourceSchema).max(10) });

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
    this.respond = deps.respond ?? respondToMockCopilot;
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
    const message: CopilotMessage = { id: this.id(), role: "user", text, createdAt: this.now(),
      analysisId: SAMPLE_ANALYSIS_ID, replyState: "pending" };
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
    const controller = new AbortController();
    this.controller = controller;
    this.update({ messages: this.state.messages.map(m => m.id === messageId ? { ...m, replyState: "pending" } : m),
      pendingId: messageId, error: null });
    try {
      const reply = replySchema.parse(await this.respond({ question: message.text,
        history: this.state.messages.filter(m => m.id !== messageId).slice(-20).map(({ role, text }) => ({ role, text })) }, controller.signal));
      if (controller.signal.aborted || this.controller !== controller) return;
      this.controller = null;
      this.update({ messages: [...this.state.messages.map(m => m.id === messageId ? { ...m, replyState: "completed" as const } : m),
        { id: this.id(), role: "assistant", createdAt: this.now(), analysisId: SAMPLE_ANALYSIS_ID, ...reply }], pendingId: null });
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
