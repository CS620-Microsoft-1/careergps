import { ApiError } from "./api/client.ts";

export type AuthUser = { id: string; email?: string | null };
export type AccountState<Profile> = {
  status: "loading" | "ready"; email: string | null; authUserId: string | null; user: Profile | null;
};
type Dependencies<Profile, Changes> = {
  currentUser: () => Promise<AuthUser | null>;
  subscribe: (changed: (user: AuthUser | null) => void) => () => void;
  loadProfile: (expectedUserId: string) => Promise<Profile | null>;
  updateProfile: (changes: Changes, expectedUserId: string) => Promise<Profile>;
  publish: (state: AccountState<Profile>) => void;
  ownerChanged?: () => void;
  defer?: (work: () => void) => void;
};

/** Follow the shared login while discarding work started for an older account. */
export class AccountSession<Profile extends { id: string }, Changes> {
  private state: AccountState<Profile> = { status: "loading", email: null, authUserId: null, user: null };
  private generation = 0;
  private active = false;
  private identified = false;
  private unsubscribe: (() => void) | null = null;

  private readonly deps: Dependencies<Profile, Changes>;

  constructor(deps: Dependencies<Profile, Changes>) { this.deps = deps; }

  start() {
    this.active = true;
    this.unsubscribe = this.deps.subscribe(this.identify);
    const generation = this.generation;
    void this.deps.currentUser().then(user => {
      if (this.active && this.generation === generation) this.identify(user);
    }).catch(() => {
      if (this.active && this.generation === generation) this.identify(null);
    });
  }

  stop() {
    this.active = false;
    this.generation++;
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  private publish(state: AccountState<Profile>) {
    this.state = state;
    this.deps.publish(state);
  }

  private identify = (user: AuthUser | null) => {
    if (!this.active) return;
    const id = user?.id ?? null;
    const email = user?.email ?? null;
    if (this.identified && id === this.state.authUserId) {
      // Same-user sign-in/token refresh leaves the conversation and draft mounted.
      if (email !== this.state.email) this.publish({ ...this.state, email });
      return;
    }
    this.identified = true;
    const generation = ++this.generation;
    this.deps.ownerChanged?.();
    this.publish({ status: id ? "loading" : "ready", email, authUserId: id, user: null });
    if (!id) return;
    // Auth callbacks stay synchronous; profile/API work runs after the SDK event completes.
    (this.deps.defer ?? (work => { setTimeout(work, 0); }))(() => {
      if (!this.active || this.generation !== generation) return;
      void this.deps.loadProfile(id).then(profile => {
        if (this.active && this.generation === generation) {
          this.publish({ ...this.state, status: "ready", user: profile?.id === id ? profile : null });
        }
      }).catch(() => {
        if (this.active && this.generation === generation) this.publish({ ...this.state, status: "ready", user: null });
      });
    });
  };

  async update(changes: Changes, expectedUserId: string): Promise<Profile> {
    const owner = this.state.authUserId;
    const generation = this.generation;
    if (!this.active || !owner || owner !== expectedUserId || this.state.status !== "ready") throw this.accountChanged();
    const profile = await this.deps.updateProfile(changes, owner);
    if (!this.active || generation !== this.generation || profile.id !== owner) throw this.accountChanged();
    this.publish({ ...this.state, user: profile });
    return profile;
  }

  private accountChanged() {
    return new ApiError(409, "Account changed", "Your signed-in account changed. Please try again from the current account.");
  }
}
