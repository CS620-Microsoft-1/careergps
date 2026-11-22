import { expect, test, type Page } from "@playwright/test";

import { account, hasAccount } from "../support/account";
import { mockApi } from "../support/mock-api";

// Deleting the account from Profile. DELETE /me is answered by the mock, so the test account survives.
test.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");

const DELETE_ME = { method: "DELETE", path: "/me", body: undefined };

async function openDialog(page: Page) {
  await page.goto("/profile");
  const card = page.getByRole("region", { name: "Delete account" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Delete account…" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Delete your account?" });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("the email must match before the account can be deleted; Cancel deletes nothing", async ({ page }) => {
  const api = await mockApi(page);
  const dialog = await openDialog(page);
  const confirm = dialog.getByRole("button", { name: "Delete account" });
  const input = dialog.getByLabel(/to confirm/);

  await expect(confirm).toBeDisabled();
  await input.fill("someone-else@example.edu");
  await expect(confirm).toBeDisabled();
  await input.fill(` ${account.email.toUpperCase()} `);
  await expect(confirm).toBeEnabled();

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  expect(api.calls).not.toContainEqual(DELETE_ME);
});

test("deleting signs out and confirms on the login page", async ({ page }) => {
  const api = await mockApi(page);
  // Even a local sign-out revokes the session in Supabase, and every signed-in test shares this one.
  const logouts: string[] = [];
  await page.route("**/auth/v1/logout**", (route) => {
    logouts.push(route.request().url());
    return route.fulfill({ status: 204 });
  });
  const dialog = await openDialog(page);
  await dialog.getByLabel(/to confirm/).fill(account.email);
  await dialog.getByRole("button", { name: "Delete account" }).click();

  await page.waitForURL("**/login?deleted=1");
  await expect(page.getByRole("status").filter({ hasText: "Your account has been deleted." })).toBeVisible();
  expect(api.calls.filter((call) => call.method === "DELETE" && call.path === "/me")).toHaveLength(1);
  expect(logouts).toHaveLength(1);
});

test("a failed deletion shows the error and stays on Profile", async ({ page }) => {
  await mockApi(page, { deleteAccountStatus: 502 });
  const dialog = await openDialog(page);
  await dialog.getByLabel(/to confirm/).fill(account.email);
  await dialog.getByRole("button", { name: "Delete account" }).click();

  await expect(dialog.getByRole("alert")).toHaveText("We couldn't delete your account. Try again.");
  await expect(dialog.getByRole("button", { name: "Delete account" })).toBeEnabled();
  expect(new URL(page.url()).pathname).toBe("/profile");
});
