import { expect, test } from "@playwright/test";

import { resources } from "../../test/fixtures";
import type { Resource } from "../../types/api";
import { hasAccount } from "../support/account";
import { mockApi } from "../support/mock-api";

// The shared Data Analyst student on Resources: recommended certifications on top, the rest under "More certifications".
test.skip(!hasAccount, "Set E2E_EMAIL and E2E_PASSWORD to run the signed-in tests.");

const certification = (id: string, title: string, skills: string[]): Resource => ({
  id, type: "certification", title, provider: "Example", meta: "Beginner · $100 · Exam fee", description: "",
  skills, url: "https://example.com/cert", school: null, alongside: false,
});

const withCertifications: Resource[] = [...resources,
  certification("cert-sql", "SQL Associate", ["sql"]),
  certification("cert-dashboards", "Dashboard Specialist", ["dashboarding"]),
  certification("cert-scripting", "Python Scripting", ["analytical_scripting"]),
  certification("cert-both", "Data Analyst Professional", ["sql", "dashboarding"]),
];

test("recommended certifications show on top; the rest open under More certifications", async ({ page }) => {
  await mockApi(page, { resources: withCertifications, certificationPicks: ["cert-both", "cert-sql"] });
  await page.goto("/resources");
  const section = page.getByRole("region", { name: "Certifications" });
  const more = section.getByRole("group");

  const top = section.getByRole("article").filter({ hasText: "Recommended" });
  await expect(top).toHaveCount(2);
  await expect(top.nth(0)).toContainText("Data Analyst Professional");
  await expect(top.nth(1)).toContainText("SQL Associate");
  await expect(section.getByRole("article")).toHaveCount(2);

  await more.getByText("More certifications").click();
  await expect(more.getByRole("article")).toHaveCount(2);
  await expect(more.getByRole("article").nth(0)).toContainText("Dashboard Specialist");
  await expect(more.getByRole("article").nth(1)).toContainText("Python Scripting");
});
