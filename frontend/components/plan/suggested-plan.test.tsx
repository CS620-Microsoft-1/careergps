import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePlan } from "@/components/plan/plan-provider";
import { SuggestedPlan } from "@/components/plan/suggested-plan";
import { getActionPlanSuggestions } from "@/lib/api/action-plans";
import { ApiError } from "@/lib/api/client";
import { actionPlanSuggestions, planItem, resources } from "@/test/fixtures";
import type { ActionPlanSuggestions } from "@/types/api";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));
vi.mock("@/lib/api/action-plans", () => ({ getActionPlanSuggestions: vi.fn() }));

const addPlan = vi.fn();

function mockPlan(savedIds: string[] = []) {
  const items = savedIds.map((id) => planItem(id));
  vi.mocked(usePlan).mockReturnValue({
    family: "data_analyst", status: "ready", resources, items,
    saved: new Map(items.map((item) => [item.resource_id, item])), pending: new Set(),
    justCompleted: null, justSaved: null, setStatus: vi.fn(), remove: vi.fn(), toggleSaved: vi.fn(), addPlan,
  });
}

function suggestions(overrides: Partial<ActionPlanSuggestions> = {}, plan: object = {}): ActionPlanSuggestions {
  return { ...actionPlanSuggestions, ...overrides, plans: [{ ...actionPlanSuggestions.plans[0], ...plan }] };
}

async function renderReady(response = suggestions()) {
  vi.mocked(getActionPlanSuggestions).mockResolvedValue(response);
  const onClose = vi.fn();
  render(<SuggestedPlan family="data_analyst" onClose={onClose} />);
  await screen.findByRole("heading", { name: "SQL first, then dashboards" });
  return onClose;
}

describe("SuggestedPlan", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    addPlan.mockResolvedValue(true);
    mockPlan();
  });

  it("asks for the role's plan and shows that it is working", async () => {
    vi.mocked(getActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    render(<SuggestedPlan family="data_analyst" onClose={vi.fn()} />);
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

  it("marks items already in the plan", async () => {
    mockPlan(["sql-project"]);
    await renderReady();
    expect(screen.getAllByText("In your plan")).toHaveLength(1);
    const card = screen.getByText("Analyze a public dataset with SQL").closest("li")!;
    expect(within(card).getByText("In your plan")).toBeInTheDocument();
  });

  it("adds the main path in order and the alongside items separately, then closes", async () => {
    const onClose = await renderReady();
    await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
    expect(addPlan).toHaveBeenCalledWith(["sql-course", "sql-project", "dashboard-course"], ["data-club"]);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("stays open when adding fails", async () => {
    addPlan.mockResolvedValue(false);
    const onClose = await renderReady();
    await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows the backend's message and asks again on Try again", async () => {
    vi.mocked(getActionPlanSuggestions)
      .mockRejectedValueOnce(new ApiError(409, "failed", "The skill gap analysis has not finished yet"))
      .mockResolvedValueOnce(suggestions());
    render(<SuggestedPlan family="data_analyst" onClose={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The skill gap analysis has not finished yet");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "SQL first, then dashboards" })).toBeInTheDocument();
    expect(getActionPlanSuggestions).toHaveBeenCalledTimes(2);
  });

  it("closes from Cancel while loading and from Dismiss when ready", async () => {
    vi.mocked(getActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    const onCancel = vi.fn();
    const { unmount } = render(<SuggestedPlan family="data_analyst" onClose={onCancel} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
    unmount();

    const onClose = await renderReady();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(addPlan).not.toHaveBeenCalled();
  });

  it("states hours, coverage gaps and a rule plan only when they apply", async () => {
    await renderReady();
    expect(screen.getByText(/About 12 hours of project work\./)).toBeInTheDocument();
    expect(screen.queryByText(/Built from your gap ranking/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No resource closes/)).not.toBeInTheDocument();
  });

  it("notes a rule plan, unknown hours and an uncovered gap", async () => {
    await renderReady(suggestions({ source: "rules", uncovered_skill_ids: ["statistics"] }, { project_hours: null }));
    expect(screen.queryByText(/hours of project work/)).not.toBeInTheDocument();
    expect(screen.getByText(/Built from your gap ranking\./)).toBeInTheDocument();
    expect(screen.getByText(/No resource closes statistics yet\./i)).toBeInTheDocument();
  });
});
