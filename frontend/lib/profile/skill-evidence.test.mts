import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import type { ResumeClassification } from "@/types/api";

import { mentions, rateSkills } from "./skill-evidence.ts";

const example = JSON.parse(
  readFileSync(new URL("../../../docs/resume-classification-example.json", import.meta.url), "utf8"),
) as ResumeClassification;

const empty: ResumeClassification = {
  personal_information: {},
  research_interests: [],
  education: [],
  work_experience: [],
  research_experience: [],
  projects: [],
  technical_skills: [],
  languages: [],
  publications: [],
  awards_honors: [],
  certifications: [],
  leadership_activities: [],
  other: [],
};

describe("rateSkills", () => {
  it("rates the docs example by where each skill is shown", () => {
    const rated = Object.fromEntries(rateSkills(example).map((s) => [s.skill, s]));
    assert.equal(rated.Python.level, "strong");
    assert.equal(rated.SQL.level, "strong");
    assert.equal(rated.Tableau.level, "some");
    assert.equal(rated.Statistics.level, "none");
    assert.deepEqual(rated.Python.sources, [
      "Data Analyst, Northstar Labs",
      "Project: Career Insights Dashboard",
    ]);
    assert.deepEqual(rated.Statistics.sources, []);
  });

  it("adds project technologies that are not listed, without duplicates", () => {
    const rated = rateSkills({
      ...empty,
      technical_skills: ["python", " ", "Python"],
      projects: [{ name: "Bot", url: null, technologies: ["Python", "Docker"], content: [] }],
    });
    assert.deepEqual(
      rated.map((s) => [s.skill, s.level]),
      [
        ["python", "some"],
        ["Docker", "some"],
      ],
    );
  });

  it("counts research and leadership entries as strong evidence", () => {
    const rated = rateSkills({
      ...empty,
      technical_skills: ["R", "Figma"],
      research_experience: [
        { organization: "Lab", title: "RA", content: ["Modeled outcomes in R."] },
      ],
      leadership_activities: [
        { organization: "Club", role: "Design lead", content: ["Ran Figma workshops."] },
      ],
    });
    assert.deepEqual(
      rated.map((s) => [s.skill, s.level, s.sources]),
      [
        ["R", "strong", ["RA, Lab"]],
        ["Figma", "strong", ["Design lead, Club"]],
      ],
    );
  });

  it("returns nothing for a résumé with no skills", () => {
    assert.deepEqual(rateSkills(empty), []);
  });
});

describe("mentions", () => {
  it("matches whole words only", () => {
    assert.equal(mentions("Built tools in Java.", "Java"), true);
    assert.equal(mentions("Built tools in JavaScript.", "Java"), false);
    assert.equal(mentions("Wrote C++ services", "C++"), true);
    assert.equal(mentions("Wrote C++ services", "C"), false);
    assert.equal(mentions("APIs in Node.js", "node.js"), true);
    assert.equal(mentions("Used C# daily", "C#"), true);
    assert.equal(mentions("", "SQL"), false);
  });
});
