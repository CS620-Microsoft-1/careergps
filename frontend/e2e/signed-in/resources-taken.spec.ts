import { expect, test, type Page } from "@playwright/test";

import { hasAccount } from "../support/account";
import { mockApi } from "../support/mock-api";
import { uwResources } from "../support/uw-courses";

// The shared Data Analyst student, at UW–Madison, marking school courses taken on Resources.
test.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");

const COURSE = "/me/courses/uw-cs-564";
const SAVE = { method: "PUT", path: COURSE, body: { source: "manual" } };
const REMOVE = { method: "DELETE", path: COURSE, body: undefined };

/** The UW course cards on the Resources page. */
const courseGroup = (page: Page) => page.getByRole("region", { name: "Courses at UW–Madison" });

test("marking a course taken hides it; Undo brings it back", async ({ page }) => {
  const api = await mockApi(page, { resources: uwResources });
  await page.goto("/resources");
  const courses = courseGroup(page);
  const card = courses.getByRole("article").filter({ hasText: "COMP SCI 564" });
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Mark taken" }).click();
  await expect(card).toHaveCount(0);
  const undoBar = page.getByRole("status").filter({ hasText: "Marked COMP SCI 564 as taken" });
  await expect(undoBar).toBeVisible();
  await expect.poll(() => api.calls).toContainEqual(SAVE);

  await undoBar.getByRole("button", { name: "Undo" }).click();
  await expect(card).toBeVisible();
  await expect(undoBar).toHaveCount(0);
  await expect.poll(() => api.calls).toContainEqual(REMOVE);
  expect(api.taken.size).toBe(0);
});

test("Undo waits until the course is saved, so its DELETE can't overtake the PUT", async ({ page }) => {
  const api = await mockApi(page, { resources: uwResources });
  const release = api.holdCourseSaves();
  await page.goto("/resources");
  const card = courseGroup(page).getByRole("article").filter({ hasText: "COMP SCI 564" });
  await card.getByRole("button", { name: "Mark taken" }).click();
  const undo = page.getByRole("status").filter({ hasText: "Marked COMP SCI 564 as taken" })
    .getByRole("button", { name: "Undo" });
  await expect.poll(() => api.calls).toContainEqual(SAVE);
  await expect(undo).toBeDisabled();

  release();
  await expect(undo).toBeEnabled();
  await undo.click();
  await expect(card).toBeVisible();
  await expect.poll(() => api.calls.filter((call) => call.path === COURSE).map((call) => call.method))
    .toEqual(["PUT", "DELETE"]);
  expect(api.taken.size).toBe(0);
});

test("Not now hides a résumé suggestion and saves nothing", async ({ page }) => {
  const api = await mockApi(page, { resources: uwResources, resumeCourseMatches: ["uw-cs-564"] });
  await page.goto("/resources");
  const suggestion = page.getByText("Found in your résumé: COMP SCI 564");
  await expect(suggestion).toBeVisible();

  await page.getByRole("button", { name: "Not now" }).click();
  await expect(suggestion).toHaveCount(0);
  await page.reload();
  await expect(courseGroup(page).getByRole("article").filter({ hasText: "COMP SCI 564" })).toBeVisible();
  await expect(suggestion).toHaveCount(0);
  expect(api.calls.filter((call) => call.method === "PUT" && call.path === COURSE)).toEqual([]);
  // One list per account is covered in lib/dismissed-courses.test.mts.
});

test("Show N taken reveals a taken course, and Taken un-marks it", async ({ page }) => {
  const api = await mockApi(page, { resources: uwResources, takenCourses: ["uw-cs-564"] });
  await page.goto("/resources");
  const courses = courseGroup(page);
  const card = courses.getByRole("article").filter({ hasText: "COMP SCI 564" });
  await expect(courses.getByRole("article").filter({ hasText: "COMP SCI 320" })).toBeVisible();
  await expect(card).toHaveCount(0);

  await courses.getByRole("button", { name: "Show 1 taken" }).click();
  await expect(card).toBeVisible();
  const taken = card.getByRole("button", { name: "Taken", exact: true });
  await expect(taken).toHaveAttribute("aria-pressed", "true");

  await taken.click();
  await expect(card.getByRole("button", { name: "Mark taken" })).toBeVisible();
  // Nothing is taken any more, so the toggle goes away and the card stays in the normal list.
  await expect(courses.getByRole("button", { name: "Hide taken" })).toHaveCount(0);
  await expect(card).toBeVisible();
  await expect.poll(() => api.taken.size).toBe(0);
});
