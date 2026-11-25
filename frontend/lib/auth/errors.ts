import type { AuthError } from "@supabase/supabase-js";

const GENERIC = "Something went wrong. Try again.";

// Supabase Auth error codes → what the user should do. Unknown codes get the generic message.
const MESSAGES: Partial<Record<string, string>> = {
  invalid_credentials: "Email or password is incorrect.",
  email_not_confirmed: "Confirm your email first. Check your inbox for the link we sent.",
  weak_password: "Choose a stronger password.",
  email_address_invalid: "Enter a valid email address.",
  // Supabase refused to email this address (e.g. its built-in mailer only reaches team members).
  email_address_not_authorized: "We couldn't send a confirmation email to this address. Try a different email.",
  over_email_send_rate_limit: "Too many emails sent. Try again in an hour.",
  over_request_rate_limit: "Too many attempts. Wait a few minutes and try again.",
  signup_disabled: "Sign-up is closed right now.",
  // University mail scanners often open the link first and confirm the email, so signing in usually works.
  flow_state_expired: "This link was already used. Your email may already be confirmed. Try signing in.",
  otp_expired: "This link was already used or has expired. Your email may already be confirmed. Try signing in.",
  same_password: "Choose a password different from your current one.",
};

// A reset link that can't be used: the student needs a new one, not a hint about confirming.
const EXPIRED_RESET_LINK = "This reset link has expired or was already used. Request a new one.";
const RECOVERY_MESSAGES: Partial<Record<string, string>> = {
  otp_expired: EXPIRED_RESET_LINK,
  flow_state_expired: EXPIRED_RESET_LINK,
  // Not a recovery link at all (no token, or a different type).
  missing_token: "This reset link is incomplete. Request a new one.",
};

/** A message for a Supabase error code, e.g. the error_code a confirmation link comes back with. */
export function authCodeMessage(code: string | null | undefined) {
  return (code && MESSAGES[code]) || GENERIC;
}

/** Like authCodeMessage, for the password reset link. null means the link carried no token. */
export function recoveryCodeMessage(code: string | null | undefined) {
  return RECOVERY_MESSAGES[code ?? "missing_token"] ?? authCodeMessage(code);
}

const UNREACHABLE = "Can't reach the sign-in service. Check your connection and try again.";
const isNetworkError = (error: AuthError) =>
  error.status === 0 || error.name === "AuthRetryableFetchError";

/** A message for the user. Never shows Supabase's raw text, which can leak details. */
export function authErrorMessage(error: AuthError) {
  return isNetworkError(error) ? UNREACHABLE : authCodeMessage(error.code);
}

/** authErrorMessage for the password reset steps (verifying the link, saving the password). */
export function recoveryErrorMessage(error: AuthError) {
  // An error without a code is not a missing token, so it gets the generic message.
  return isNetworkError(error) ? UNREACHABLE : error.code ? recoveryCodeMessage(error.code) : GENERIC;
}
