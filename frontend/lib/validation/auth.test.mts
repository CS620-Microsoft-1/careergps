import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { forgotPasswordSchema, resetPasswordSchema } from "./auth.ts";

describe("forgotPasswordSchema", () => {
  it("needs a valid email", () => {
    assert.equal(forgotPasswordSchema.safeParse({ email: "student@wisc.edu" }).success, true);
    assert.equal(forgotPasswordSchema.safeParse({ email: "not-an-email" }).success, false);
  });
});

describe("resetPasswordSchema", () => {
  it("accepts a matching password of at least 8 characters", () => {
    const result = resetPasswordSchema.safeParse({ password: "longenough", confirmPassword: "longenough" });
    assert.equal(result.success, true);
  });

  it("reports a mismatch on the confirm field", () => {
    const result = resetPasswordSchema.safeParse({ password: "longenough", confirmPassword: "different1" });
    assert.equal(result.success, false);
    assert.deepEqual(result.error?.issues.map((issue) => issue.path), [["confirmPassword"]]);
  });

  it("applies the sign-up length rules", () => {
    assert.equal(resetPasswordSchema.safeParse({ password: "short", confirmPassword: "short" }).success, false);
    const long = "x".repeat(129);
    assert.equal(resetPasswordSchema.safeParse({ password: long, confirmPassword: long }).success, false);
  });
});
