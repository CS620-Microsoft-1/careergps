import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { TooltipProvider } from "@/components/ui/tooltip";
import { homeFor } from "@/lib/auth/account";
import { getSupabase } from "@/lib/supabase/client";

const replace = vi.fn();
const signInWithPassword = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth/account", () => ({ homeFor: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ getSupabase: vi.fn() }));

// The app's root layout provides this; the form's "Forgot password?" tooltip needs it.
const renderForm = () => render(<TooltipProvider><LoginForm /></TooltipProvider>);

async function fillIn(email: string, password: string) {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

describe("LoginForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSupabase).mockReturnValue(
      { auth: { signInWithPassword, signOut: vi.fn().mockResolvedValue({}) } } as unknown as ReturnType<typeof getSupabase>,
    );
    vi.mocked(homeFor).mockResolvedValue("/dashboard");
  });

  it("asks for an email and password before signing in", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(signInWithPassword).not.toHaveBeenCalled();
  });

  it("signs in and goes to the student's home", async () => {
    signInWithPassword.mockResolvedValue({ error: null });
    renderForm();
    await fillIn("student@example.edu", "correct horse");
    expect(signInWithPassword).toHaveBeenCalledWith({ email: "student@example.edu", password: "correct horse" });
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows the sign-in error and stays on the page", async () => {
    signInWithPassword.mockResolvedValue({
      error: { name: "AuthApiError", status: 400, code: "invalid_credentials", message: "Invalid login credentials" },
    });
    renderForm();
    await fillIn("student@example.edu", "wrong");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
