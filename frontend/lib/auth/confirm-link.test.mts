import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { readConfirmLink } from "./confirm-link.ts";

describe("readConfirmLink", () => {
  it("reads a token link", () => {
    assert.deepEqual(readConfirmLink("?token_hash=abc&type=email", ""), {
      kind: "token",
      tokenHash: "abc",
      type: "email",
    });
  });

  it("accepts the signup type and falls back to email for anything else", () => {
    assert.equal(readConfirmLink("?token_hash=abc&type=signup", "").kind === "token", true);
    assert.deepEqual(readConfirmLink("?token_hash=abc&type=recovery", ""), {
      kind: "token",
      tokenHash: "abc",
      type: "email",
    });
  });

  it("reports Supabase's error from the query or the fragment", () => {
    assert.deepEqual(readConfirmLink("", "#error=access_denied&error_code=otp_expired"), {
      kind: "error",
      code: "otp_expired",
    });
    assert.deepEqual(readConfirmLink("?error_code=flow_state_expired", ""), {
      kind: "error",
      code: "flow_state_expired",
    });
  });

  it("treats a link without a token as already used", () => {
    assert.deepEqual(readConfirmLink("?code=xyz", ""), { kind: "error", code: "otp_expired" });
    assert.deepEqual(readConfirmLink("", ""), { kind: "error", code: "otp_expired" });
  });
});
