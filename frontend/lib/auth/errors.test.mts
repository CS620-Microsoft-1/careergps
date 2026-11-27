import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { AuthError } from "@supabase/supabase-js";

import { authCodeMessage, recoveryCodeMessage, recoveryErrorMessage } from "./errors.ts";

// Only the fields the message helpers read.
const authError = (fields: { code?: string; status?: number; name?: string }) =>
  ({ name: "AuthApiError", status: 400, ...fields }) as AuthError;

describe("recoveryCodeMessage", () => {
  it("asks for a new link when the reset link is used up", () => {
    assert.match(recoveryCodeMessage("otp_expired"), /Request a new one/);
    assert.match(recoveryCodeMessage("flow_state_expired"), /Request a new one/);
    assert.match(recoveryCodeMessage(null), /incomplete/);
  });

  it("falls back to the shared messages", () => {
    assert.equal(recoveryCodeMessage("weak_password"), authCodeMessage("weak_password"));
    assert.equal(recoveryCodeMessage("same_password"), "Choose a password different from your current one.");
    assert.equal(recoveryCodeMessage("something_new"), "Something went wrong. Try again.");
  });
});

describe("recoveryErrorMessage", () => {
  it("maps Supabase errors without showing their raw text", () => {
    assert.match(recoveryErrorMessage(authError({ code: "otp_expired" })), /Request a new one/);
    assert.equal(recoveryErrorMessage(authError({})), "Something went wrong. Try again.");
    assert.match(recoveryErrorMessage(authError({ status: 0 })), /Can't reach/);
  });
});
