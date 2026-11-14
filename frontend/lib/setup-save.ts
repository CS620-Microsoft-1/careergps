/**
 * The end of first-time setup saves the account and résumé while the route page is already open.
 * Setup starts the save and navigates at once; the route page waits for it here before it loads
 * the saved profile. The save lives outside any component, so it keeps going after setup is hidden.
 */
export type SetupSaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "failed"; error: string };

/** One request of the save. Steps run in order; a retry starts again at the one that failed. */
export type SetupSaveStep = () => Promise<void>;

const IDLE: SetupSaveState = { status: "idle" };

let state: SetupSaveState = IDLE;
let steps: SetupSaveStep[] = [];
let toMessage: (error: unknown) => string = () => "Couldn’t save your profile. Try again.";
/** Each save gets its own id, so a step finishing late can't advance a newer save. */
let current = 0;
const listeners = new Set<() => void>();

function set(next: SetupSaveState) {
  state = next;
  listeners.forEach((listener) => listener());
}

async function run(id: number) {
  set({ status: "saving" });
  try {
    while (steps.length) {
      await steps[0]();
      if (id !== current) return;
      // Done: a retry must not repeat it (a second résumé upload would add a duplicate version).
      steps = steps.slice(1);
    }
    set(IDLE);
  } catch (error) {
    if (id === current) set({ status: "failed", error: toMessage(error) });
  }
}

/** Start the save; the route page shows it as the first loading step. Ignored while one is running. */
export function startSetupSave(save: SetupSaveStep[], message: (error: unknown) => string): boolean {
  if (state.status === "saving") return false;
  steps = save;
  toMessage = message;
  void run(++current);
  return true;
}

/** Continue a failed save from the step that failed. */
export function retrySetupSave() {
  if (state.status === "failed") void run(current);
}

export const setupSave = {
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
  getSnapshot: () => state,
  getServerSnapshot: () => IDLE,
};
