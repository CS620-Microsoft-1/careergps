import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";
import { getSupabase } from "@/lib/supabase/client";

const resetPasswordForEmail = vi.fn();

vi.mock("@/lib/supabase/client", () => ({ getSupabase: vi.fn() }));

async function requestLink(email: string) {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
}

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/forgot-password");
    vi.mocked(getSupabase).mockReturnValue(
      { auth: { resetPasswordForEmail } } as unknown as ReturnType<typeof getSupabase>,
    );
  });

  it("asks for a valid email before sending", async () => {
    render(<ForgotPasswordForm />);
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(resetPasswordForEmail).not.toHaveBeenCalled();
  });

  it("sends a link that lands on /auth/reset and shows the inbox screen", async () => {
    resetPasswordForEmail.mockResolvedValue({ error: null });
    render(<ForgotPasswordForm />);
    await requestLink("student@example.edu");
    expect(resetPasswordForEmail).toHaveBeenCalledWith("student@example.edu", {
      redirectTo: `${window.location.origin}/auth/reset`,
    });
    expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send again in \d+s/ })).toBeDisabled();
  });

  it("doesn't reveal whether the account exists", async () => {
    resetPasswordForEmail.mockResolvedValue({
      error: { name: "AuthApiError", status: 400, code: "user_not_found", message: "User not found" },
    });
    render(<ForgotPasswordForm />);
    await requestLink("nobody@example.edu");
    expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows rate limits and stays on the form", async () => {
    resetPasswordForEmail.mockResolvedValue({
      error: { name: "AuthApiError", status: 429, code: "over_email_send_rate_limit", message: "rate limit" },
    });
    render(<ForgotPasswordForm />);
    await requestLink("student@example.edu");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many emails sent");
    expect(screen.queryByText("Check your inbox")).not.toBeInTheDocument();
  });

  it("prefills the email passed from the login page", async () => {
    window.history.replaceState(null, "", "/forgot-password?email=student%40example.edu");
    render(<ForgotPasswordForm />);
    await vi.waitFor(() => expect(screen.getByLabelText("Email")).toHaveValue("student@example.edu"));
  });
});
