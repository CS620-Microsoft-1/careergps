import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";

import { dismissedKey, readDismissed, writeDismissed } from "./dismissed-courses.ts";

const store = new Map<string, string>();
const storage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => { store.set(key, value); },
};

describe("dismissed résumé course suggestions", () => {
  beforeEach(() => {
    store.clear();
    Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
  });

  it("keeps one list per account", () => {
    writeDismissed("ada", ["uw-cs-400", "uw-cs-564"]);
    assert.deepEqual(readDismissed("ada"), ["uw-cs-400", "uw-cs-564"]);
    assert.deepEqual(readDismissed("grace"), []);
    assert.notEqual(dismissedKey("ada"), dismissedKey("grace"));
  });

  it("reads nothing from a missing, broken or unexpected value", () => {
    assert.deepEqual(readDismissed("ada"), []);
    store.set(dismissedKey("ada"), "{not json");
    assert.deepEqual(readDismissed("ada"), []);
    store.set(dismissedKey("ada"), JSON.stringify({ ids: ["uw-cs-400"] }));
    assert.deepEqual(readDismissed("ada"), []);
    store.set(dismissedKey("ada"), JSON.stringify(["uw-cs-400", 7, null]));
    assert.deepEqual(readDismissed("ada"), ["uw-cs-400"]);
  });

  it("does not throw when storage is blocked", () => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get() { throw new Error("blocked"); },
    });
    writeDismissed("ada", ["uw-cs-400"]);
    assert.deepEqual(readDismissed("ada"), []);
  });
});
