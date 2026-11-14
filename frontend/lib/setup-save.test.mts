import assert from "node:assert/strict";
import { it } from "node:test";

import { retrySetupSave, setupSave, startSetupSave } from "./setup-save.ts";

const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

it("ignores a second save while one is running, and retries only the step that failed", async () => {
  const calls: string[] = [];
  let failAccount = true;
  let finishUpload!: () => void;
  const upload = new Promise<void>((resolve) => { finishUpload = resolve; });
  const steps = [
    () => { calls.push("resume"); return upload; },
    async () => { calls.push("account"); if (failAccount) throw new Error("offline"); },
  ];

  assert.equal(startSetupSave(steps, () => "failed"), true);
  // A double click while saving: no second save, so no second résumé.
  assert.equal(startSetupSave(steps, () => "failed"), false);
  finishUpload();
  await settled();
  assert.deepEqual(setupSave.getSnapshot(), { status: "failed", error: "failed" });

  failAccount = false;
  retrySetupSave();
  assert.equal(setupSave.getSnapshot().status, "saving");
  await settled();
  assert.deepEqual(setupSave.getSnapshot(), { status: "idle" });
  assert.deepEqual(calls, ["resume", "account", "account"]);
});
