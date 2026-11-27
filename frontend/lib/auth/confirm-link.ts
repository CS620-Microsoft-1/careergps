// What an email confirmation link carries, read from its query string and fragment.

// Link types the confirmation email may carry (docs/supabase/confirm-signup.html sends "email").
const TOKEN_TYPES = ["email", "signup"] as const;
export type TokenType = (typeof TOKEN_TYPES)[number];

export type ConfirmLink =
  /** Confirmed only when the student presses the button (verifyOtp). */
  | { kind: "token"; tokenHash: string; type: TokenType }
  /** Supabase's error_code (e.g. otp_expired), or null for a link with no token at all. */
  | { kind: "error"; code: string | null };

/** search and hash as in window.location, e.g. "?token_hash=abc&type=email" and "". */
export function readConfirmLink(search: string, hash: string): ConfirmLink {
  const params = new URLSearchParams(search + hash.replace("#", "&"));
  if (params.has("error_code")) return { kind: "error", code: params.get("error_code") };
  const tokenHash = params.get("token_hash");
  if (tokenHash) {
    const type = TOKEN_TYPES.find((t) => t === params.get("type")) ?? "email";
    return { kind: "token", tokenHash, type };
  }
  // No token: e.g. a ?code= link from Supabase's default template, which isn't used. Supabase has
  // already confirmed the email by then, so the message suggests signing in.
  return { kind: "error", code: "otp_expired" };
}

export type RecoveryLink =
  /** Used only when the student submits a new password, so mail scanners can't spend it. */
  | { kind: "token"; tokenHash: string }
  /** Supabase's error_code, or null for a link that isn't a recovery link at all. */
  | { kind: "error"; code: string | null };

/**
 * A password reset link (docs/supabase/reset-password.html sends ?token_hash=…&type=recovery).
 * Only type=recovery is accepted, so a sign-up link can't be used to set a password.
 */
export function readRecoveryLink(search: string, hash: string): RecoveryLink {
  const params = new URLSearchParams(search + hash.replace("#", "&"));
  if (params.has("error_code")) return { kind: "error", code: params.get("error_code") };
  const tokenHash = params.get("token_hash");
  if (tokenHash && params.get("type") === "recovery") return { kind: "token", tokenHash };
  return { kind: "error", code: null };
}
