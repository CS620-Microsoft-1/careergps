import { expect, test } from "./mock-api";

const REMINDER = "You took COMP SCI 564, which covers this. Add it to your résumé.";
const COURSE_TILE = "COMP SCI 564: Database Management Systems";
const CERTIFICATION_TILE = "Microsoft Certified: Fabric Analytics Engineer Associate";

test("a taken course leaves the suggestions and becomes a reminder", async ({ page, api }) => {
  api.taken.add("uw-cs-564");
  await page.goto("/gaps");
  const gap = page.getByRole("region", { name: /Data modeling/ });
  await expect(gap.getByText(REMINDER)).toBeVisible();
  // The first gap opens by default; its suggestions no longer include the course.
  await expect(gap.getByText(CERTIFICATION_TILE)).toBeVisible();
  await expect(gap.getByText(COURSE_TILE)).toHaveCount(0);
  await expect(gap.getByRole("link", { name: /Browse all 2 resources/ })).toBeVisible();
  // The score did not change.
  await expect(page.getByText("40% match")).toBeVisible();
});

test("without taken courses there is no reminder and the course is suggested", async ({ page }) => {
  await page.goto("/gaps");
  const gap = page.getByRole("region", { name: /Data modeling/ });
  await expect(gap.getByText(COURSE_TILE)).toBeVisible();
  await expect(gap.getByText(/You took/)).toHaveCount(0);
  await expect(gap.getByRole("link", { name: /Browse all 3 resources/ })).toBeVisible();
});
