import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDestinationRuns, type Destinations } from "@/components/destinations/use-destination-runs";
import { HomeView } from "@/components/home/home-view";
import { useSwitchRoute } from "@/components/layout/use-switch-route";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { planItem, report, resources, resume, run, user } from "@/test/fixtures";
import type { PlanItem } from "@/types/api";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));
vi.mock("@/components/skill-gaps/skill-gap-provider", () => ({ useSkillGapAnalysis: vi.fn() }));
vi.mock("@/components/layout/account-provider", () => ({ useAccount: () => ({ user }) }));
vi.mock("@/components/layout/use-switch-route", () => ({ useSwitchRoute: vi.fn() }));
vi.mock("@/components/destinations/use-destination-runs", async (importActual) => ({
  ...await importActual<typeof import("@/components/destinations/use-destination-runs")>(),
  useDestinationRuns: vi.fn(),
}));

type Analysis = ReturnType<typeof useSkillGapAnalysis>;
type Plan = ReturnType<typeof usePlan>;

function mockAnalysis(overrides: Partial<Analysis> = {}) {
  vi.mocked(useSkillGapAnalysis).mockReturnValue({
    loaded: true, family: "data_analyst", run, submitting: false, restoring: false, elapsed: 0, awaiting: null,
    snapshot: { user_id: user.id, resume_id: resume.id, filename: resume.original_filename,
      confirmed_at: resume.created_at, job_family: "data_analyst" },
    analyze: vi.fn(), changeFamily: vi.fn(), reload: vi.fn(), checkAgain: vi.fn(),
    ...overrides,
  });
}

function mockPlan(items: PlanItem[] = [], overrides: Partial<Plan> = {}) {
  vi.mocked(usePlan).mockReturnValue({
    family: "data_analyst", status: "ready", resources, items,
    saved: new Map(items.map((item) => [item.resource_id, item])), pending: new Set(),
    justCompleted: null, justSaved: null, setStatus: vi.fn(), remove: vi.fn(), toggleSaved: vi.fn(),
    ...overrides,
  });
}

const emptyRun = { status: "missing" as const, run: null };
function mockDestinations(overrides: Partial<Destinations> = {}) {
  vi.mocked(useDestinationRuns).mockReturnValue({
    families: ["data_analyst"], resumes: {},
    runs: { data_analyst: { status: "ready", run }, software_engineer: emptyRun, ai_engineer: emptyRun },
    ...overrides,
  });
}

const switchTo = vi.fn();
const section = (name: string) => within(screen.getByRole("heading", { name }).closest("section")!);

describe("HomeView", () => {
  beforeEach(() => {
    switchTo.mockReset();
    vi.mocked(useSwitchRoute).mockReturnValue({ family: "data_analyst", locked: false, switchTo });
    mockAnalysis();
    mockPlan();
    mockDestinations();
  });

  it("shows the match, the goal and what it was matched against", () => {
    render(<HomeView />);
    expect(screen.getByRole("heading", { level: 1, name: "You’re 42% of the way there" })).toBeInTheDocument();
    expect(screen.getByText("Your goal · Data analyst · Madison, WI")).toBeInTheDocument();
    expect(screen.getByText("Matched with sam-resume.pdf against 200 data analyst postings.")).toBeInTheDocument();
  });

  it("lists the biggest gaps, each linking to resources that close it", () => {
    render(<HomeView />);
    const gaps = section("Skills to build");
    expect(gaps.getByRole("link", { name: "Ways to close the SQL gap" })).toHaveAttribute("href", "/resources?gap=sql");
    expect(gaps.getByRole("link", { name: "Ways to close the Dashboard development gap" }))
      .toHaveAttribute("href", "/resources?gap=dashboarding");
    expect(gaps.getByRole("link", { name: "Ways to close the SQL gap" })).toHaveTextContent("See ways to close it");
    // Strengths and skills to review aren't gaps.
    expect(gaps.queryByText("Analytical scripting")).not.toBeInTheDocument();
    expect(gaps.queryByText("Statistics")).not.toBeInTheDocument();
    expect(gaps.getByRole("link", { name: "See all gaps" })).toHaveAttribute("href", "/gaps");
    // Postings aren't filtered by location, so the note doesn't name one.
    expect(gaps.getByText("Based on 200 job postings for this role.")).toBeInTheDocument();
  });

  it("says so when there are no gaps left", () => {
    const strong = report.skills.filter((skill) => skill.skill_id === "analytical_scripting");
    mockAnalysis({ run: { ...run, report: { ...report, skills: strong, priority_order: [] } } });
    render(<HomeView />);
    expect(section("Skills to build").getByText(/No gaps left for this role/)).toBeInTheDocument();
  });

  it("points an empty plan at resources for the biggest gap", () => {
    render(<HomeView />);
    expect(screen.getByRole("heading", { level: 2, name: "Your plan is empty" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add resources" })).toHaveAttribute("href", "/resources?gap=sql");
  });

  it("shows the first saved step as the next turn", () => {
    mockPlan([planItem("sql-course")]);
    render(<HomeView />);
    const card = within(screen.getByRole("heading", { level: 2, name: "SQL for Data Analysis" }).closest("section")!);
    expect(card.getByText("SQL", { selector: "b" })).toBeInTheDocument();
    expect(card.getByText("Queries, joins and aggregates.")).toBeInTheDocument();
    expect(card.getByRole("link", { name: "Start this step" })).toHaveAttribute("href", "https://example.com/sql");
    expect(card.getByRole("link", { name: "See action plan" })).toHaveAttribute("href", "/plan");
  });

  it("skips done steps when picking the next turn", () => {
    mockPlan([planItem("sql-course", "done"), planItem("sql-project")]);
    render(<HomeView />);
    const card = within(screen.getByRole("heading", { level: 2, name: "Analyze a public dataset with SQL" }).closest("section")!);
    // No link of its own, so the step opens the action plan.
    expect(card.getByRole("link", { name: "Start this step" })).toHaveAttribute("href", "/plan");
  });

  it("waits for the plan before picking a next turn", () => {
    mockPlan([], { status: "loading" });
    render(<HomeView />);
    expect(screen.getByText("Loading your plan…")).toBeInTheDocument();
    expect(screen.queryByText("Your plan is empty")).not.toBeInTheDocument();
  });

  it("offers to explore more when the student has one destination", () => {
    render(<HomeView />);
    expect(screen.getByRole("link", { name: /Explore more destinations/ })).toHaveAttribute("href", "/onboarding?step=role");
    // The selected destination is the goal above, not one of the others.
    expect(screen.queryByRole("button", { name: /Data analyst/ })).not.toBeInTheDocument();
  });

  it("lists the other destinations and switches to one on click", async () => {
    const other = { ...run, id: "run-2", job_family: "software_engineer" as const, match: { ...run.match!, score: 0.7 } };
    mockDestinations({
      families: ["data_analyst", "software_engineer", "ai_engineer"],
      resumes: { software_engineer: { job_family: "software_engineer", resume_id: "resume-2",
        original_filename: "sam-swe.pdf", created_at: run.created_at } },
      runs: { data_analyst: { status: "ready", run }, software_engineer: { status: "ready", run: other }, ai_engineer: emptyRun },
    });
    render(<HomeView />);
    const swe = screen.getByRole("button", { name: /Software engineer/ });
    expect(swe).toHaveTextContent("70%");
    expect(swe).toHaveTextContent("sam-swe.pdf");
    expect(screen.getByRole("button", { name: /AI engineer/ })).toHaveTextContent("Not analyzed yet");
    // Every role is added, so exploring opens Destinations instead of adding one.
    expect(screen.getByRole("link", { name: /Explore more destinations/ })).toHaveAttribute("href", "/destinations");

    await userEvent.click(swe);
    expect(switchTo).toHaveBeenCalledWith("software_engineer");
  });

  it("locks the other destinations while a switch can't happen", () => {
    vi.mocked(useSwitchRoute).mockReturnValue({ family: "data_analyst", locked: true, switchTo });
    mockDestinations({ families: ["data_analyst", "software_engineer"] });
    render(<HomeView />);
    expect(screen.getByRole("button", { name: /Software engineer/ })).toBeDisabled();
  });

  it("eases the page in after a destination switch, but not on the first load", () => {
    const { container, rerender } = render(<HomeView />);
    expect(container.firstElementChild).not.toHaveClass("entrance-rise");
    // Switching clears the run while the new role's analysis loads.
    mockAnalysis({ run: null, restoring: true });
    rerender(<HomeView />);
    mockAnalysis();
    rerender(<HomeView />);
    expect(container.firstElementChild).toHaveClass("entrance-rise");
  });

  it("shows the analysis gate until the analysis is ready", () => {
    mockAnalysis({ loaded: false, run: null, snapshot: null });
    render(<HomeView />);
    expect(screen.getByRole("heading", { level: 1, name: "Your route" })).toBeInTheDocument();
    expect(screen.getByText("Loading your route…")).toBeInTheDocument();
  });
});
