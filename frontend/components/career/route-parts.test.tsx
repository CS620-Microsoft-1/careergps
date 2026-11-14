import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MatchRing, SaveButton } from "@/components/career/route-parts";
import { usePlan } from "@/components/plan/plan-provider";
import { planItem } from "@/test/fixtures";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));

type Plan = ReturnType<typeof usePlan>;

function mockPlan(overrides: Partial<Plan> = {}) {
  const plan: Plan = {
    family: "data_analyst", status: "ready", resources: [], items: [], saved: new Map(), pending: new Set(),
    justCompleted: null, justSaved: null, setStatus: vi.fn(), remove: vi.fn(), toggleSaved: vi.fn(),
    ...overrides,
  };
  vi.mocked(usePlan).mockReturnValue(plan);
  return plan;
}

describe("MatchRing", () => {
  it("shows the match as a whole percent", () => {
    render(<MatchRing value={0.423} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("match")).toBeInTheDocument();
  });

  it("shows a dash while the match is unknown", () => {
    render(<MatchRing value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("leaves the label out of small rings", () => {
    render(<MatchRing value={0.5} size={72} />);
    expect(screen.queryByText("match")).not.toBeInTheDocument();
  });
});

describe("SaveButton", () => {
  beforeEach(() => vi.mocked(usePlan).mockReset());

  it("saves an unsaved resource", async () => {
    const plan = mockPlan();
    render(<SaveButton resourceId="sql-course" />);
    const button = screen.getByRole("button", { name: "Save to plan" });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(button);
    expect(plan.toggleSaved).toHaveBeenCalledWith("sql-course");
  });

  it("shows a saved resource as pressed", () => {
    mockPlan({ saved: new Map([["sql-course", planItem("sql-course")]]) });
    render(<SaveButton resourceId="sql-course" />);
    expect(screen.getByRole("button", { name: "Saved to plan" })).toHaveAttribute("aria-pressed", "true");
  });

  it("is disabled while the save is in flight", () => {
    mockPlan({ pending: new Set(["sql-course"]) });
    render(<SaveButton resourceId="sql-course" />);
    expect(screen.getByRole("button", { name: "Save to plan" })).toBeDisabled();
  });

  it("shows Done instead of a button once the step is done", () => {
    mockPlan({ saved: new Map([["sql-course", planItem("sql-course", "done")]]) });
    render(<SaveButton resourceId="sql-course" />);
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("pops the saved icon only for the resource saved a moment ago", () => {
    const saved = new Map([["sql-course", planItem("sql-course")], ["sql-project", planItem("sql-project")]]);
    mockPlan({ saved, justSaved: "sql-course" });
    const { container } = render(<><SaveButton resourceId="sql-course" /><SaveButton resourceId="sql-project" /></>);
    expect(container.querySelectorAll("svg.entrance-pop")).toHaveLength(1);
    expect(screen.getAllByRole("button")[0].querySelector("svg.entrance-pop")).not.toBeNull();
  });
});
