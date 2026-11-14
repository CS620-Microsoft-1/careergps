import { expect, test } from "@playwright/test";

import { hasAccount } from "../support/account";
import { mockApi } from "../support/mock-api";
import { uwResources } from "../support/uw-courses";

// The shared Data Analyst student, at UW–Madison: COMP SCI 564 is one of three ways to close the SQL gap.
test.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");

const REMINDER = "You took COMP SCI 564, which covers this. Add it to your résumé.";
const COURSE_TILE = "COMP SCI 564: Database Management Systems";
const OTHER_TILE = "SQL for Data Analysis";

test("a taken course leaves the suggestions and becomes a reminder", async ({ page }) => {
  await mockApi(page, { resources: uwResources, takenCourses: ["uw-cs-564"] });
  await page.goto("/gaps");
  const gap = page.getByRole("region", { name: /SQL/ });
  await expect(gap.getByText(REMINDER)).toBeVisible();
  // The first gap opens by default; its suggestions no longer include the course.
  await expect(gap.getByText(OTHER_TILE)).toBeVisible();
  await expect(gap.getByText(COURSE_TILE)).toHaveCount(0);
  await expect(gap.getByRole("link", { name: /Browse all 2 resources/ })).toBeVisible();
  // The score did not change.
  await expect(page.getByText("42% match")).toBeVisible();
});

test("without taken courses there is no reminder and the course is suggested", async ({ page }) => {
  await mockApi(page, { resources: uwResources });
  await page.goto("/gaps");
  const gap = page.getByRole("region", { name: /SQL/ });
  await expect(gap.getByText(COURSE_TILE)).toBeVisible();
  await expect(gap.getByText(/You took/)).toHaveCount(0);
  await expect(gap.getByRole("link", { name: /Browse all 3 resources/ })).toBeVisible();
});
