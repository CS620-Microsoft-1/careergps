/**
 * The end of first-time setup saves the account and résumé while the route page is already open.
 * Setup starts the save and navigates at once; the route page waits for it here before it loads
 * the saved profile. The save lives outside any component, so it keeps going after setup is hidden.
 */
export type SetupSaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "failed"; error: string };

const IDLE: SetupSaveState = { status: "idle" };

let state: SetupSaveState = IDLE;
let task: (() => Promise<void>) | null = null;
let toMessage: (error: unknown) => string = () => "Couldn’t save your profile. Try again.";
const listeners = new Set<() => void>();

function set(next: SetupSaveState) {
  state = next;
  listeners.forEach((listener) => listener());
}

function run() {
  if (!task) return;
  const current = task;
  set({ status: "saving" });
  current().then(
    () => { if (task === current) { task = null; set(IDLE); } },
    (error: unknown) => { if (task === current) set({ status: "failed", error: toMessage(error) }); },
  );
}

/** Start the save; the route page shows it as the first loading step. */
export function startSetupSave(save: () => Promise<void>, message: (error: unknown) => string) {
  task = save;
  toMessage = message;
  run();
}

/** Run the same save again after it failed. */
export function retrySetupSave() {
  if (state.status === "failed") run();
}

export const setupSave = {
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
  getSnapshot: () => state,
  getServerSnapshot: () => IDLE,
};
