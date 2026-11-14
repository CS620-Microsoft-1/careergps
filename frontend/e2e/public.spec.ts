import { expect, test } from "@playwright/test";

// Signed out. The redirects come from proxy.ts, which only checks sessions when Supabase is configured.
const supabaseConfigured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY);

test.describe("signed out", () => {
  test("the root sends visitors to log in", async ({ page }) => {
    test.skip(!supabaseConfigured, "Needs NEXT_PUBLIC_SUPABASE_* in frontend/.env");
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("a protected page sends visitors to log in and back", async ({ page }) => {
    test.skip(!supabaseConfigured, "Needs NEXT_PUBLIC_SUPABASE_* in frontend/.env");
    await page.goto("/gaps");
    await expect(page).toHaveURL(/\/login\?next=%2Fgaps$/);
  });

  test("login checks the form before signing in", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    await expect(page.getByText("Enter your password.")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("login links to sign up", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page).toHaveURL(/\/signup$/);
  });
});
