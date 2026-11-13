import { expect, test } from "./mock-api";

/** The UW course cards on the Resources page. */
const courseGroup = (page: import("@playwright/test").Page) =>
  page.getByRole("region", { name: "Courses at UW–Madison" });

test("marking a course taken hides it; Undo brings it back", async ({ page, api }) => {
  await page.goto("/resources");
  const courses = courseGroup(page);
  const card = courses.getByRole("article").filter({ hasText: "COMP SCI 564" });
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Mark taken" }).click();
  await expect(card).toHaveCount(0);
  const undoBar = page.getByRole("status").filter({ hasText: "Marked COMP SCI 564 as taken" });
  await expect(undoBar).toBeVisible();
  await expect.poll(() => api.calls).toContain("PUT /me/courses/uw-cs-564");

  await undoBar.getByRole("button", { name: "Undo" }).click();
  await expect(card).toBeVisible();
  await expect(undoBar).toHaveCount(0);
  await expect.poll(() => api.calls).toContain("DELETE /me/courses/uw-cs-564");
  expect(api.taken.size).toBe(0);
});

test("Undo waits until the course is saved, so its DELETE can't overtake the PUT", async ({ page, api }) => {
  const release = api.holdSaves();
  await page.goto("/resources");
  const card = courseGroup(page).getByRole("article").filter({ hasText: "COMP SCI 564" });
  await card.getByRole("button", { name: "Mark taken" }).click();
  const undo = page.getByRole("status").filter({ hasText: "Marked COMP SCI 564 as taken" })
    .getByRole("button", { name: "Undo" });
  await expect.poll(() => api.calls).toContain("PUT /me/courses/uw-cs-564");
  await expect(undo).toBeDisabled();

  release();
  await expect(undo).toBeEnabled();
  await undo.click();
  await expect(card).toBeVisible();
  await expect.poll(() => api.calls.filter((call) => call.endsWith(" /me/courses/uw-cs-564")))
    .toEqual(["PUT /me/courses/uw-cs-564", "DELETE /me/courses/uw-cs-564"]);
  expect(api.taken.size).toBe(0);
});

test("Show N taken reveals a taken course, and Taken un-marks it", async ({ page, api }) => {
  api.taken.add("uw-cs-564");
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
