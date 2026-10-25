import type { ConfirmedResumeSnapshot } from "@/lib/confirmed-resume";
import type { JobFamily, SkillGapRun } from "@/types/api";

export type SkillGapSessionState = {
  loaded: boolean;
  snapshot: ConfirmedResumeSnapshot | null;
  family: JobFamily;
  run: SkillGapRun | null;
  submitting: boolean;
  restoring: boolean;
  error?: string;
  elapsed: number;
};

export type SkillGapSessionDependencies = {
  loadSnapshot: () => ConfirmedResumeSnapshot | null;
  hashResume: (snapshot: ConfirmedResumeSnapshot) => Promise<string>;
  getSavedRun: (hash: string, family: JobFamily) => string | null;
  saveRun: (hash: string, family: JobFamily, id: string) => void;
  forgetRun: (hash: string, family: JobFamily, id: string) => void;
  hasIntent: (snapshot: ConfirmedResumeSnapshot) => boolean;
  clearIntent: (snapshot: ConfirmedResumeSnapshot) => void;
  saveFamily: (snapshot: ConfirmedResumeSnapshot, family: JobFamily) => ConfirmedResumeSnapshot;
  getRun: (id: string) => Promise<SkillGapRun>;
  startRun: (snapshot: ConfirmedResumeSnapshot, family: JobFamily, force: boolean) => Promise<SkillGapRun>;
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

/** One session shared by Dashboard, Career Analysis and Skill Gaps. */
export class SkillGapSession {
  private state: SkillGapSessionState = INITIAL_STATE;
  private listeners = new Set<() => void>();
  private snapshotInitialization: Promise<void> | null = null;
  private initialRestoration: Promise<void> | null = null;
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
    void this.initialize();
    this.scheduleTimers();
    return () => {
      this.connected = false;
      this.stopTimers();
    };
  };

  initialize = async (): Promise<void> => {
    // Development effect remounts and multiple consumers share the same work.
    this.snapshotInitialization ??= this.loadInitialSnapshot();
    await this.snapshotInitialization;
    const snapshot = this.state.snapshot;
    if (snapshot && this.connected) {
      this.initialRestoration ??= this.restore(snapshot, snapshot.job_family, true);
      await this.initialRestoration;
    }
  };

  private update(patch: Partial<SkillGapSessionState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  private async loadInitialSnapshot() {
    try {
      const snapshot = this.deps.loadSnapshot();
      if (snapshot && await this.deps.hashResume(snapshot) !== snapshot.review_hash) {
        throw new Error("The local résumé snapshot changed. Review and confirm it again.");
      }
      // Show the dashboard as soon as its confirmed input is ready. Restoring
      // or submitting work must remain visible, rather than blocking this flag.
      this.update({ snapshot, ...(snapshot ? { family: snapshot.job_family } : {}),
        loaded: true, restoring: Boolean(snapshot) });
    } catch (error) {
      this.update({ loaded: true, restoring: false, error: this.deps.errorMessage(error) });
    }
  }

  private accept(run: SkillGapRun, snapshot: ConfirmedResumeSnapshot, family: JobFamily, expectedId?: string) {
    if (run.resume_hash !== snapshot.review_hash || run.job_family !== family
        || (expectedId !== undefined && run.id !== expectedId)) {
      throw new Error("This analysis belongs to a different résumé or direction. Start a new analysis.");
    }
    return run;
  }

  private receive(run: SkillGapRun) {
    this.update({ run, error: undefined, elapsed: this.elapsedFor(run) });
    this.scheduleTimers();
  }

  private async restore(snapshot: ConfirmedResumeSnapshot, family: JobFamily, allowAutoStart: boolean) {
    const generation = ++this.generation;
    this.update({ restoring: true });
    try {
      const intent = this.deps.hasIntent(snapshot);
      const id = this.deps.getSavedRun(snapshot.review_hash, family);
      // Consume before awaiting requests. Failed/404 restores must not silently
      // turn a page visit or refresh into a replacement model request.
      if (intent) this.deps.clearIntent(snapshot);
      if (id) {
        try {
          const run = this.accept(await this.deps.getRun(id), snapshot, family, id);
          if (generation === this.generation) this.receive(run);
        } catch (error) {
          if (generation !== this.generation) return;
          if (this.deps.isNotFound(error)) {
            try { this.deps.forgetRun(snapshot.review_hash, family, id); } catch { /* Keep the missing run unselected. */ }
            this.update({ run: null,
              error: "The saved analysis is no longer available. Choose Analyze to start a new one." });
          } else this.update({ error: this.deps.errorMessage(error) });
        }
      } else if (allowAutoStart && intent && this.connected && generation === this.generation) {
        this.update({ restoring: false });
        await this.analyze(false);
      }
    } catch (error) {
      if (generation === this.generation) this.update({ error: this.deps.errorMessage(error) });
    } finally {
      if (generation === this.generation) this.update({ restoring: false });
    }
  }

  analyze = async (force: boolean): Promise<void> => {
    const { snapshot, family, run, submitting, restoring, loaded } = this.state;
    if (!loaded || !snapshot || submitting || restoring || isActiveSkillGapRun(run)) return;
    const generation = this.generation;
    // Synchronous lock covers automatic confirmation and double-clicks alike.
    this.update({ submitting: true, error: undefined });
    try {
      this.deps.clearIntent(snapshot);
      const next = this.accept(await this.deps.startRun(snapshot, family, force), snapshot, family);
      if (generation !== this.generation) return;
      this.receive(next);
      try { this.deps.saveRun(snapshot.review_hash, family, next.id); }
      catch {
        this.update({ error: "Analysis started, but this tab could not save its link. Keep this page open to see the result." });
      }
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
    try {
      const selected = value as JobFamily;
      const next = this.deps.saveFamily(snapshot, selected);
      this.stopTimers();
      this.update({ snapshot: next, family: selected, run: null, error: undefined, elapsed: 0 });
      void this.restore(next, selected, false);
    } catch (error) { this.update({ error: this.deps.errorMessage(error) }); }
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
    if (!this.connected || !isActiveSkillGapRun(this.state.run)) {
      this.stopTimers();
      return;
    }
    if (this.pollTimer === undefined && !this.pollInFlight) {
      this.pollTimer = this.deps.setTimer(() => {
        this.pollTimer = undefined;
        void this.poll();
      }, delay);
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
        try { this.deps.forgetRun(snapshot.review_hash, family, run.id); } catch { /* Do not keep a missing run busy. */ }
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
