import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlanBuilding, TICKER_MS } from "@/components/plan/plan-building";
import type { ActionPlanBuildStage } from "@/types/api";

const GAPS: ActionPlanBuildStage = { type: "stage", stage: "gaps",
  gaps: [{ skill_id: "sql", skill_name: "SQL" }, { skill_id: "dashboarding", skill_name: "Dashboard development" }] };
const CANDIDATES: ActionPlanBuildStage = { type: "stage", stage: "candidates",
  counts: { project: 3, certification: 1, student_org: 1 },
  samples: [{ title: "SQL project", type: "project" }, { title: "SQL certificate", type: "certification" }] };
const stage = (name: "agent" | "checking" | "cached" | "rules"): ActionPlanBuildStage => ({ type: "stage", stage: name });

// The animated counter is a web component jsdom can't run; plain text is enough here.
vi.mock("@number-flow/react", () => ({ default: ({ value }: { value: number }) => <>{value}</> }));

/** Each step's state, from its screen-reader suffix (top-level steps only, not the gap chips). */
function states() {
  const list = screen.getByRole("list", { name: "Plan building steps" });
  return [...list.querySelectorAll(":scope > li")]
    .map((step) => step.querySelector("p")?.textContent?.match(/: (done|in progress|waiting)$/)?.[1]);
}

function setReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query.includes("reduce"), media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}

describe("PlanBuilding", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts by reading the gaps", () => {
    render(<PlanBuilding stages={[]} onCancel={vi.fn()} />);
    expect(states()).toEqual(["in progress", "waiting", "waiting", "waiting"]);
    expect(screen.getByRole("status")).toHaveTextContent("Reading your gaps");
  });

  it("shows the real gaps and shortlist counts as they arrive", () => {
    render(<PlanBuilding stages={[GAPS, CANDIDATES]} onCancel={vi.fn()} />);
    const steps = screen.getByRole("list", { name: "Plan building steps" });
    expect(within(steps).getByText("Read your 2 gaps")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Your gaps" })).getAllByRole("listitem").map((gap) => gap.textContent))
      .toEqual(["SQL", "Dashboard development"]);
    expect(within(steps).getByText("Shortlisted 5 resources that close them")).toBeInTheDocument();
    expect(states()).toEqual(["done", "done", "waiting", "waiting"]);
    // Between stages, screen readers keep the latest finished one.
    expect(screen.getByRole("status")).toHaveTextContent("Shortlisted 5 resources that close them");
  });

  it("cycles through the real shortlist while the mentor decides", () => {
    setReducedMotion(false);
    vi.useFakeTimers();
    render(<PlanBuilding stages={[GAPS, CANDIDATES, stage("agent")]} onCancel={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Your mentor is choosing and ordering the steps");
    expect(screen.getByText("SQL project")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(TICKER_MS); });
    expect(screen.getByText("SQL certificate")).toBeInTheDocument();
  });

  it("keeps the shortlist still under reduced motion", async () => {
    setReducedMotion(true);
    render(<PlanBuilding stages={[GAPS, CANDIDATES, stage("agent")]} onCancel={vi.fn()} />);
    expect(await screen.findByText("Weighing SQL project, SQL certificate and more")).toBeInTheDocument();
  });

  it("moves on to checking once the mentor answers", () => {
    render(<PlanBuilding stages={[GAPS, CANDIDATES, stage("agent"), stage("checking")]} onCancel={vi.fn()} />);
    expect(states()).toEqual(["done", "done", "done", "in progress"]);
  });

  it("says when a cached plan is used", () => {
    render(<PlanBuilding stages={[GAPS, CANDIDATES, stage("cached")]} onCancel={vi.fn()} />);
    expect(within(screen.getByRole("list", { name: "Plan building steps" }))
      .getByText("Found the plan your mentor already built")).toBeInTheDocument();
  });

  it("says when the mentor is unavailable and the gap ranking is used", () => {
    render(<PlanBuilding stages={[GAPS, CANDIDATES, stage("agent"), stage("rules")]} onCancel={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Mentor unavailable, building from your gap ranking instead");
  });

  it("counts the elapsed time and can be cancelled", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onCancel = vi.fn();
    render(<PlanBuilding stages={[]} onCancel={onCancel} />);
    act(() => { vi.advanceTimersByTime(65_000); });
    expect(screen.getByText("1:05")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
