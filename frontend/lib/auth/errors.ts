import type { AuthError } from "@supabase/supabase-js";

const GENERIC = "Something went wrong. Try again.";

// Supabase Auth error codes → what the user should do. Unknown codes get the generic message.
const MESSAGES: Partial<Record<string, string>> = {
  invalid_credentials: "Email or password is incorrect.",
  email_not_confirmed: "Confirm your email first. Check your inbox for the link we sent.",
  weak_password: "Choose a stronger password.",
  email_address_invalid: "Enter a valid email address.",
  // The built-in Supabase mailer only sends to members of the project's organization.
  email_address_not_authorized: "We can't send email to this address yet. Use a team member's email.",
  over_email_send_rate_limit: "Too many emails sent. Try again in an hour.",
  over_request_rate_limit: "Too many attempts. Wait a few minutes and try again.",
  signup_disabled: "Sign-up is closed right now.",
  flow_state_expired: "This link has expired or was already used. Try signing in.",
  otp_expired: "This link has expired or was already used. Try signing in.",
};

/** A message for a Supabase error code, e.g. the error_code a confirmation link comes back with. */
export function authCodeMessage(code: string | null | undefined) {
  return (code && MESSAGES[code]) || GENERIC;
}

/** A message for the user. Never shows Supabase's raw text, which can leak details. */
export function authErrorMessage(error: AuthError) {
  if (error.status === 0 || error.name === "AuthRetryableFetchError") {
    return "Can't reach the sign-in service. Check your connection and try again.";
  }
  return authCodeMessage(error.code);
}
