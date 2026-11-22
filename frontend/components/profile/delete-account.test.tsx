import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { confirmsEmail, DeleteAccount } from "@/components/profile/delete-account";
import { ApiError } from "@/lib/api/client";
import { deleteAccount } from "@/lib/api/me";
import { getSupabase } from "@/lib/supabase/client";

const EMAIL = "student@example.edu";
const signOut = vi.fn();
const replace = vi.fn();

vi.mock("@/components/layout/account-provider", () => ({ useAccount: () => ({ email: EMAIL }) }));
vi.mock("@/lib/api/me", () => ({ deleteAccount: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ getSupabase: vi.fn() }));

async function openDialog() {
  render(<DeleteAccount />);
  await userEvent.click(screen.getByRole("button", { name: "Delete account…" }));
  return screen.getByRole("button", { name: "Delete account" });
}

describe("confirmsEmail", () => {
  it("ignores case and surrounding spaces, and needs an email", () => {
    expect(confirmsEmail("  Student@Example.EDU ", EMAIL)).toBe(true);
    expect(confirmsEmail("student@example.ed", EMAIL)).toBe(false);
    expect(confirmsEmail("", null)).toBe(false);
  });
});

describe("DeleteAccount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signOut.mockResolvedValue({});
    vi.mocked(getSupabase).mockReturnValue({ auth: { signOut } } as unknown as ReturnType<typeof getSupabase>);
    vi.stubGlobal("location", { ...window.location, replace });
  });

  it("keeps the delete button disabled until the email matches", async () => {
    const confirm = await openDialog();
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/to confirm/), "student@example");
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/to confirm/), ".EDU");
    expect(confirm).toBeEnabled();
    expect(deleteAccount).not.toHaveBeenCalled();
  });

  it("deletes, signs out and goes to the login page", async () => {
    vi.mocked(deleteAccount).mockResolvedValue();
    const confirm = await openDialog();
    await userEvent.type(screen.getByLabelText(/to confirm/), EMAIL);
    await userEvent.click(confirm);

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/login?deleted=1"));
    expect(deleteAccount).toHaveBeenCalledTimes(1);
    expect(signOut).toHaveBeenCalledWith({ scope: "local" });
  });

  it("shows the error and stays signed in when deletion fails", async () => {
    vi.mocked(deleteAccount).mockRejectedValue(
      new ApiError(502, "DELETE /me failed with 502", "We couldn't delete your account. Try again."));
    const confirm = await openDialog();
    await userEvent.type(screen.getByLabelText(/to confirm/), EMAIL);
    await userEvent.click(confirm);

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't delete your account. Try again.");
    expect(signOut).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete account" })).toBeEnabled();
  });

  it("says deletion is unavailable when the server isn't configured", async () => {
    vi.mocked(deleteAccount).mockRejectedValue(new ApiError(503, "DELETE /me failed with 503"));
    const confirm = await openDialog();
    await userEvent.type(screen.getByLabelText(/to confirm/), EMAIL);
    await userEvent.click(confirm);

    expect(await screen.findByRole("alert")).toHaveTextContent("isn't available right now");
    expect(replace).not.toHaveBeenCalled();
  });
});
