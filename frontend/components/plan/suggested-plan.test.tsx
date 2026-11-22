import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePlan } from "@/components/plan/plan-provider";
import { SuggestedPlan } from "@/components/plan/suggested-plan";
import { getActionPlanSuggestions } from "@/lib/api/action-plans";
import { ApiError } from "@/lib/api/client";
import { actionPlanSuggestions, planItem, resources } from "@/test/fixtures";
import type { ActionPlanSuggestions, PlanItem } from "@/types/api";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));
vi.mock("@/lib/api/action-plans", () => ({ getActionPlanSuggestions: vi.fn() }));

const addItems = vi.fn();
const remove = vi.fn();
const GAP_ORDER = ["sql", "dashboarding", "statistics"];
const ALL_ENTRIES = [{ resourceId: "sql-course", position: 1 }, { resourceId: "sql-project", position: 2 },
  { resourceId: "dashboard-course", position: 3 }, { resourceId: "data-club" }];

function mockPlan(items: PlanItem[] = [], pending: string[] = []) {
  vi.mocked(usePlan).mockReturnValue({
    family: "data_analyst", status: "ready", resources, items,
    saved: new Map(items.map((item) => [item.resource_id, item])), pending: new Set(pending),
    justCompleted: null, justSaved: null, setStatus: vi.fn(), remove, toggleSaved: vi.fn(), addItems,
  });
}

function suggestions(overrides: Partial<ActionPlanSuggestions> = {}, plan: object = {}): ActionPlanSuggestions {
  return { ...actionPlanSuggestions, ...overrides, plans: [{ ...actionPlanSuggestions.plans[0], ...plan }] };
}

function renderPanel(onClose = vi.fn()) {
  render(<SuggestedPlan family="data_analyst" gapOrder={GAP_ORDER} onClose={onClose} />);
  return onClose;
}

async function renderReady(response = suggestions()) {
  vi.mocked(getActionPlanSuggestions).mockResolvedValue(response);
  const onClose = renderPanel();
  await screen.findByRole("heading", { name: "SQL first, then dashboards" });
  return onClose;
}

const card = (title: string) => screen.getByText(title).closest("li")!;
const skillChips = () => within(screen.getByRole("list", { name: "Skills this plan builds" })).getAllByRole("listitem")
  .map((chip) => chip.textContent);

describe("SuggestedPlan", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    addItems.mockResolvedValue(true);
    mockPlan();
  });

  it("asks for the role's plan and shows that it is working", async () => {
    vi.mocked(getActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    renderPanel();
    expect(await screen.findByRole("status")).toHaveTextContent("Building your plan");
    expect(getActionPlanSuggestions).toHaveBeenCalledWith("data_analyst", { signal: expect.any(AbortSignal) });
  });

  it("shows the plan in order, with each mentor reason and the alongside items", async () => {
    await renderReady();
    const steps = within(screen.getByRole("list", { name: "Main path, in order" })).getAllByRole("listitem");
    expect(steps.map((step) => within(step).getByText(/^Step \d:/, { exact: false }).closest("p")?.textContent)).toEqual([
      "Step 1: SQL for Data Analysis", "Step 2: Analyze a public dataset with SQL", "Step 3: Building Dashboards",
    ]);
    expect(within(steps[0]).getByText("Learn joins and aggregates before you query real data.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Alongside" })).getByText("Data Science Club")).toBeInTheDocument();
  });

  describe("skills highlight", () => {
    it("lists the covered skills in gap order with their step counts and marks the top gap", async () => {
      await renderReady();
      expect(skillChips()).toEqual(["1SQL · top gap · 2 steps", "2Dashboard development · 1 step"]);
    });

    it("shows a gap no resource closes as not covered yet", async () => {
      await renderReady(suggestions({ uncovered_skill_ids: ["statistics"] }));
      expect(skillChips()).toContain("3Statistics · not covered yet");
      expect(screen.getByText("2 of 3")).toBeInTheDocument();
    });

    it("counts gaps, steps, alongside items and project hours", async () => {
      await renderReady();
      expect(screen.getByText("2 of 2")).toBeInTheDocument();
      expect(screen.getByText("3 steps")).toBeInTheDocument();
      expect(screen.getByText("+ 1 alongside")).toBeInTheDocument();
      expect(screen.getByText("≈ 12 h")).toBeInTheDocument();
    });

    it("leaves out the hours when no project has an estimate", async () => {
      await renderReady(suggestions({}, { project_hours: null }));
      expect(screen.queryByText(/of project work/)).not.toBeInTheDocument();
    });
  });

  describe("adding", () => {
    it("adds a single main-path card with its step number as position", async () => {
      await renderReady();
      await userEvent.click(within(card("Analyze a public dataset with SQL")).getByRole("button", { name: /Add to plan/ }));
      expect(addItems).toHaveBeenCalledWith([{ resourceId: "sql-project", position: 2 }]);
    });

    it("adds an alongside card without a position", async () => {
      await renderReady();
      await userEvent.click(within(card("Data Science Club")).getByRole("button", { name: /Add to plan/ }));
      expect(addItems).toHaveBeenCalledWith([{ resourceId: "data-club", position: undefined }]);
    });

    it("shows a saved card as in your plan, and pressing it again removes it", async () => {
      mockPlan([planItem("sql-project")]);
      await renderReady();
      const button = within(card("Analyze a public dataset with SQL")).getByRole("button", { name: /In your plan/ });
      expect(button).toHaveAttribute("aria-pressed", "true");
      await userEvent.click(button);
      expect(remove).toHaveBeenCalledWith("sql-project");
      expect(addItems).not.toHaveBeenCalled();
    });

    it("disables a card's button while it saves", async () => {
      mockPlan([], ["sql-course"]);
      await renderReady();
      expect(within(card("SQL for Data Analysis")).getByRole("button", { name: /Add to plan/ })).toBeDisabled();
    });

    it("adds the whole plan in order, alongside items without a position, then closes", async () => {
      const onClose = await renderReady();
      await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
      expect(addItems).toHaveBeenCalledWith(ALL_ENTRIES);
      expect(onClose).toHaveBeenCalledOnce();
    });

    it("stays open when adding fails", async () => {
      addItems.mockResolvedValue(false);
      const onClose = await renderReady();
      await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
      expect(onClose).not.toHaveBeenCalled();
    });

    it("says all in your plan once every card is saved", async () => {
      mockPlan(ALL_ENTRIES.map((entry) => planItem(entry.resourceId)));
      await renderReady();
      expect(screen.getByRole("button", { name: "All in your plan" })).toBeDisabled();
    });
  });

  it("shows the backend's message and asks again on Try again", async () => {
    vi.mocked(getActionPlanSuggestions)
      .mockRejectedValueOnce(new ApiError(409, "failed", "The skill gap analysis has not finished yet"))
      .mockResolvedValueOnce(suggestions());
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("The skill gap analysis has not finished yet");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "SQL first, then dashboards" })).toBeInTheDocument();
    expect(getActionPlanSuggestions).toHaveBeenCalledTimes(2);
  });

  it("closes from Cancel while loading and from Dismiss when ready", async () => {
    vi.mocked(getActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    const onCancel = vi.fn();
    const { unmount } = render(<SuggestedPlan family="data_analyst" gapOrder={GAP_ORDER} onClose={onCancel} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
    unmount();

    const onClose = await renderReady();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(addItems).not.toHaveBeenCalled();
  });

  it("notes a rule plan in the footer", async () => {
    await renderReady(suggestions({ source: "rules" }));
    expect(screen.getByText("Built from your gap ranking.")).toBeInTheDocument();
  });
});
