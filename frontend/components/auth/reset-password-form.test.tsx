import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResetPasswordForm } from "@/components/auth/reset-password-form";
import { homeFor } from "@/lib/auth/account";
import { getSupabase } from "@/lib/supabase/client";

const replace = vi.fn();
const verifyOtp = vi.fn();
const updateUser = vi.fn();
const signOut = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth/account", () => ({ homeFor: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ getSupabase: vi.fn() }));

const apiError = (code: string) => ({ error: { name: "AuthApiError", status: 422, code, message: code } });

async function savePassword(password: string, confirm = password) {
  await userEvent.type(screen.getByLabelText("New password"), password);
  await userEvent.type(screen.getByLabelText("Confirm password"), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Save password" }));
}

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/auth/reset?token_hash=abc&type=recovery");
    vi.mocked(getSupabase).mockReturnValue(
      { auth: { verifyOtp, updateUser, signOut } } as unknown as ReturnType<typeof getSupabase>,
    );
    verifyOtp.mockResolvedValue({ error: null });
    updateUser.mockResolvedValue({ error: null });
    signOut.mockResolvedValue({ error: null });
    vi.mocked(homeFor).mockResolvedValue("/dashboard");
  });

  it("doesn't spend the token until the student submits", async () => {
    render(<ResetPasswordForm />);
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    expect(verifyOtp).not.toHaveBeenCalled();
  });

  it("offers a new link when the link has no recovery token", async () => {
    window.history.replaceState(null, "", "/auth/reset?token_hash=abc&type=email");
    render(<ResetPasswordForm />);
    expect(await screen.findByText(/incomplete/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
  });

  it("offers a new link when Supabase sends back an expired link", async () => {
    window.history.replaceState(null, "", "/auth/reset#error=access_denied&error_code=otp_expired");
    render(<ResetPasswordForm />);
    expect(await screen.findByText(/expired or was already used/)).toBeInTheDocument();
  });

  it("checks that both passwords match before calling Supabase", async () => {
    render(<ResetPasswordForm />);
    await savePassword("new password 1", "new password 2");
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(verifyOtp).not.toHaveBeenCalled();
  });

  it("verifies the link, saves the password, signs out other devices and goes home", async () => {
    render(<ResetPasswordForm />);
    await savePassword("new password 1");
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(verifyOtp).toHaveBeenCalledWith({ token_hash: "abc", type: "recovery" });
    expect(updateUser).toHaveBeenCalledWith({ password: "new password 1" });
    expect(signOut).toHaveBeenCalledWith({ scope: "others" });
  });

  it("still goes home when signing out other devices fails", async () => {
    signOut.mockRejectedValue(new Error("offline"));
    render(<ResetPasswordForm />);
    await savePassword("new password 1");
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows a dead link screen when the token was already used", async () => {
    verifyOtp.mockResolvedValue(apiError("otp_expired"));
    render(<ResetPasswordForm />);
    await savePassword("new password 1");
    expect(await screen.findByRole("link", { name: "Request a new link" })).toBeInTheDocument();
    expect(updateUser).not.toHaveBeenCalled();
  });

  it("retries only the password save after same_password", async () => {
    updateUser.mockResolvedValueOnce(apiError("same_password"));
    render(<ResetPasswordForm />);
    await savePassword("old password 1");
    expect(await screen.findByRole("alert")).toHaveTextContent("different from your current one");

    await userEvent.clear(screen.getByLabelText("New password"));
    await userEvent.clear(screen.getByLabelText("Confirm password"));
    await savePassword("new password 1");
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(verifyOtp).toHaveBeenCalledTimes(1);
    expect(updateUser).toHaveBeenCalledTimes(2);
  });

  it("says the password was saved when the account can't be loaded", async () => {
    vi.mocked(homeFor).mockRejectedValue(new Error("API down"));
    render(<ResetPasswordForm />);
    await savePassword("new password 1");
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to log in" })).toHaveAttribute("href", "/login");
  });
});
