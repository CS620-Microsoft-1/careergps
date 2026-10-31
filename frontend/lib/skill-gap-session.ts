import type { SkillGapProfile } from "@/lib/skill-gap-profile";
import type { JobFamily, SkillGapRun } from "@/types/api";

export type SkillGapSessionState = {
  loaded: boolean;
  snapshot: SkillGapProfile | null;
  family: JobFamily;
  run: SkillGapRun | null;
  submitting: boolean;
  restoring: boolean;
  error?: string;
  elapsed: number;
};
export type SkillGapSessionDependencies = {
  /** The destination's role and résumé: the account's target role, or `family` when switching. */
  loadProfile: (family?: JobFamily) => Promise<SkillGapProfile | null>;
  consumeIntent: (profile: SkillGapProfile) => boolean;
  getLatest: (family: JobFamily) => Promise<SkillGapRun>;
  getRun: (id: string) => Promise<SkillGapRun>;
  startRun: (family: JobFamily, force: boolean) => Promise<SkillGapRun>;
  isNotFound: (error: unknown) => boolean;
  errorMessage: (error: unknown) => string;
  now: () => number;
  setTimer: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  clearTimer: (timer: ReturnType<typeof setTimeout>) => void;
};
const INITIAL_STATE: SkillGapSessionState = {
  loaded: false, snapshot: null, family: "software_engineer", run: null,
  submitting: false, restoring: false, elapsed: 0,
};
export const isActiveSkillGapRun = (run: SkillGapRun | null) =>
  run?.status === "queued" || run?.status === "running";
const sameProfile = (a: SkillGapProfile | null, b: SkillGapProfile | null) => a === b
  || (a !== null && b !== null && a.user_id === b.user_id && a.resume_id === b.resume_id && a.job_family === b.job_family);

/** Shared authenticated state. Restoring/polling only GET; POST needs a save intent or a click. */
export class SkillGapSession {
  private state: SkillGapSessionState = INITIAL_STATE;
  private listeners = new Set<() => void>();
  private initialization: Promise<void> | null = null;
  private initialRestoration: Promise<void> | null = null;
  private reloading: Promise<void> | null = null;
  private loadFailed = false;
  private switches = 0;
  private connected = false;
  private generation = 0;
  private pollInFlight = false;
  private pollTimer: ReturnType<typeof setTimeout> | undefined;
  private elapsedTimer: ReturnType<typeof setTimeout> | undefined;
  constructor(private readonly deps: SkillGapSessionDependencies) {}
  getSnapshot = () => this.state;
  getServerSnapshot = () => INITIAL_STATE;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  connect = () => {
    this.connected = true;
    // Shown again after the first load (the router hides the app while /onboarding is open): pick up a
    // new résumé or role, or recover from a failed load. An unchanged profile keeps its run.
    if (this.state.loaded && !this.reloading) {
      this.initialization = this.reloading = this.reloadProfile().finally(() => { this.reloading = null; });
    }
    void this.initialize();
    this.scheduleTimers();
    return () => { this.connected = false; this.stopTimers(); };
  };
  initialize = async (): Promise<void> => {
    this.initialization ??= this.loadInitialProfile();
    await this.initialization;
    const snapshot = this.state.snapshot;
    if (snapshot && this.connected) {
      this.initialRestoration ??= this.restore(snapshot, snapshot.job_family, this.deps.consumeIntent(snapshot));
      await this.initialRestoration;
    }
  };
  private update(patch: Partial<SkillGapSessionState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private async loadInitialProfile() {
    try {
      const snapshot = await this.deps.loadProfile();
      this.update({ snapshot, ...(snapshot ? { family: snapshot.job_family } : {}), loaded: true });
    } catch (error) {
      this.loadFailed = true;
      this.update({ loaded: true, restoring: false, error: this.deps.errorMessage(error) });
    }
  }
  /** Replaces the destination only when it changed; a failed reload keeps what is shown. */
  private async reloadProfile() {
    const switches = this.switches;
    let snapshot: SkillGapProfile | null;
    try { snapshot = await this.deps.loadProfile(); } catch { return; }
    // The student switched destination meanwhile: that choice wins.
    if (switches !== this.switches || (!this.loadFailed && sameProfile(snapshot, this.state.snapshot))) return;
    this.generation++;
    this.loadFailed = false;
    this.stopTimers();
    // initialize() then restores the new destination's run, starting a queued analysis.
    this.initialRestoration = null;
    this.update({ snapshot, ...(snapshot ? { family: snapshot.job_family } : {}), run: null, error: undefined,
      elapsed: 0, submitting: false, restoring: false });
  }
  private accept(run: SkillGapRun, snapshot: SkillGapProfile, family: JobFamily, expectedId?: string) {
    if (run.user_id !== snapshot.user_id || run.resume_id !== snapshot.resume_id || run.job_family !== family
      || (expectedId !== undefined && run.id !== expectedId)) {
      throw new Error("This analysis belongs to a different résumé or direction. Refresh before analyzing again.");
    }
    return run;
  }
  private receive(run: SkillGapRun) {
    this.update({ run, error: undefined, elapsed: this.elapsedFor(run) });
    this.scheduleTimers();
  }
  private async restore(snapshot: SkillGapProfile, family: JobFamily, allowAutoStart: boolean) {
    const generation = ++this.generation;
    this.update({ restoring: true });
    let missing = false;
    try {
      const run = this.accept(await this.deps.getLatest(family), snapshot, family);
      if (generation === this.generation) this.receive(run);
    } catch (error) {
      if (generation !== this.generation) return;
      if (this.deps.isNotFound(error)) {
        this.update({ run: null });
        missing = true;
      } else this.update({ error: this.deps.errorMessage(error) });
    } finally {
      if (generation === this.generation) this.update({ restoring: false });
    }
    if (missing && allowAutoStart && this.connected && generation === this.generation) await this.analyze(false);
  }
  analyze = async (force: boolean): Promise<void> => {
    const { snapshot, family, run, submitting, restoring, loaded } = this.state;
    if (!loaded || !snapshot || !this.connected || submitting || restoring || isActiveSkillGapRun(run)) return;
    const generation = this.generation;
    this.update({ submitting: true, error: undefined });
    try {
      const next = this.accept(await this.deps.startRun(family, force), snapshot, family);
      if (generation === this.generation) this.receive(next);
    } catch (error) {
      if (generation === this.generation) this.update({ error: this.deps.errorMessage(error) });
    } finally {
      if (generation === this.generation) this.update({ submitting: false });
    }
  };
  changeFamily = (value: string) => {
    const { snapshot, run, submitting, restoring, family } = this.state;
    if (!snapshot || submitting || restoring || isActiveSkillGapRun(run) || value === family) return;
    if (!["software_engineer", "data_analyst", "ai_engineer"].includes(value)) return;
    this.stopTimers();
    const selected = value as JobFamily;
    const generation = ++this.generation;
    this.switches++;
    this.update({ family: selected, run: null, error: undefined, elapsed: 0, restoring: true });
    // Each destination has its own résumé, so load it before restoring that role's analysis.
    void this.deps.loadProfile(selected).then((next) => {
      if (generation !== this.generation) return;
      this.update({ snapshot: next, restoring: false });
      if (next) void this.restore(next, selected, false);
    }, (error) => {
      if (generation === this.generation) this.update({ restoring: false, error: this.deps.errorMessage(error) });
    });
  };
  private elapsedFor(run: SkillGapRun) {
    return isActiveSkillGapRun(run)
      ? Math.max(run.elapsed_seconds, (this.deps.now() - Date.parse(run.created_at)) / 1000)
      : run.elapsed_seconds;
  }
  private stopTimers() {
    if (this.pollTimer !== undefined) this.deps.clearTimer(this.pollTimer);
    if (this.elapsedTimer !== undefined) this.deps.clearTimer(this.elapsedTimer);
    this.pollTimer = this.elapsedTimer = undefined;
  }
  private scheduleTimers(delay = 1500) {
    if (!this.connected || !isActiveSkillGapRun(this.state.run)) { this.stopTimers(); return; }
    if (this.pollTimer === undefined && !this.pollInFlight) {
      this.pollTimer = this.deps.setTimer(() => { this.pollTimer = undefined; void this.poll(); }, delay);
    }
    if (this.elapsedTimer === undefined) {
      this.elapsedTimer = this.deps.setTimer(() => {
        this.elapsedTimer = undefined;
        if (this.state.run) this.update({ elapsed: this.elapsedFor(this.state.run) });
        this.scheduleTimers();
      }, 1000);
    }
  }
  private async poll() {
    const { snapshot, family, run } = this.state;
    if (!this.connected || !snapshot || !run || !isActiveSkillGapRun(run)) return;
    const generation = this.generation;
    this.pollInFlight = true;
    let delay = 1500;
    try {
      const next = this.accept(await this.deps.getRun(run.id), snapshot, family, run.id);
      if (generation === this.generation) this.receive(next);
    } catch (error) {
      if (generation !== this.generation) return;
      if (this.deps.isNotFound(error)) {
        this.update({ run: null, error: "This analysis is no longer available. Choose Analyze to start a new one." });
        this.stopTimers();
      } else {
        this.update({ error: `${this.deps.errorMessage(error)} The existing analysis has not been restarted.` });
        delay = 5000;
      }
    } finally {
      this.pollInFlight = false;
      this.scheduleTimers(delay);
    }
  }
}
