import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { loginPath, safeNextPath } from "./next-path.ts";

describe("safeNextPath", () => {
  it("keeps paths on this site, with their query", () => {
    assert.equal(safeNextPath("/profile"), "/profile");
    assert.equal(safeNextPath("/gaps?role=data"), "/gaps?role=data");
  });

  it("rejects other sites", () => {
    for (const raw of ["https://evil.example", "//evil.example", "/\\evil.example", "evil.example", "/\tevil"]) {
      assert.equal(safeNextPath(raw), null, raw);
    }
  });

  it("rejects auth pages and missing values", () => {
    assert.equal(safeNextPath("/login"), null);
    assert.equal(safeNextPath("/signup?x=1"), null);
    assert.equal(safeNextPath("/auth/confirm"), null);
    assert.equal(safeNextPath(undefined), null);
    assert.equal(safeNextPath(["/profile"]), null);
  });
});

describe("loginPath", () => {
  it("remembers the current page", () => {
    assert.equal(loginPath("/profile?tab=1"), "/login?next=%2Fprofile%3Ftab%3D1");
  });

  it("drops pages not worth returning to", () => {
    assert.equal(loginPath("/"), "/login");
    assert.equal(loginPath("/login"), "/login");
  });
});
