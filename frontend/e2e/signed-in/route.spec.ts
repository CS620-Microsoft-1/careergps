import { expect, test } from "@playwright/test";

import { hasAccount } from "../support/account";
import { mockApi } from "../support/mock-api";

// Signed in as the test account, with the API mocked: a Data Analyst with a 42% match,
// gaps in SQL and dashboards, and an empty plan.
test.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");

test("Home shows the match and the biggest gaps", async ({ page }) => {
  await mockApi(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { level: 1, name: /42% of the way there/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Gaps · 2 left" })).toBeVisible();
});

test("Gaps opens a closed gap to show ways to close it", async ({ page }) => {
  await mockApi(page);
  await page.goto("/gaps");
  await expect(page.getByRole("heading", { level: 1, name: "2 gaps to close" })).toBeVisible();
  await page.getByRole("button", { name: "Show ways to close Dashboard development" }).click();
  await expect(page.getByRole("button", { name: "Hide ways to close Dashboard development" }))
    .toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Building Dashboards")).toBeVisible();
});

test("a resource saved on Resources shows up in the action plan", async ({ page }) => {
  const api = await mockApi(page);
  await page.goto("/resources");
  const card = page.getByRole("article").filter({ hasText: "SQL for Data Analysis" });
  await card.getByRole("button", { name: "Save to plan" }).click();
  await expect(card.getByRole("button", { name: "Saved to plan" })).toHaveAttribute("aria-pressed", "true");
  expect(api.calls).toContainEqual({ method: "PUT", path: "/plan/items/sql-course",
    body: { job_family: "data_analyst", status: "saved" } });

  await page.goto("/plan");
  await expect(page.getByText("SQL for Data Analysis").first()).toBeVisible();
});

test("a gap link filters Resources to that gap", async ({ page }) => {
  await mockApi(page);
  await page.goto("/resources?gap=dashboarding");
  await expect(page.getByText("Showing resources that close")).toContainText("Dashboard development");
  await expect(page.getByText("Building Dashboards")).toBeVisible();
  await expect(page.getByText("SQL for Data Analysis")).toHaveCount(0);
});

test("Destinations shows the selected role and its job market", async ({ page }) => {
  await mockApi(page);
  await page.goto("/destinations");
  // The selected destination card is the pressed one.
  await expect(page.getByRole("button", { name: /Data Analyst/, pressed: true })).toContainText("42%");
  await expect(page.getByRole("heading", { name: "Data Analyst market" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Most-asked skills" })).toBeVisible();
});
