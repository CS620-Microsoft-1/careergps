import { test as setup } from "@playwright/test";

import { AUTH_FILE, account, hasAccount } from "./support/account";
import { mockApi } from "./support/mock-api";

// Signs in once through the real login page and saves the session for the signed-in tests.
setup("sign in", async ({ page }) => {
  setup.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");
  // Login asks the API whether onboarding is finished.
  await mockApi(page);
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL("**/dashboard");
  await page.context().storageState({ path: AUTH_FILE });
});
