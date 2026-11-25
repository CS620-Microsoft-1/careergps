import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePlan } from "@/components/plan/plan-provider";
import { SuggestedPlan } from "@/components/plan/suggested-plan";
import { streamActionPlanSuggestions } from "@/lib/api/action-plans";
import { ApiError } from "@/lib/api/client";
import { actionPlanSuggestions, planItem, resources } from "@/test/fixtures";
import type { ActionPlanSuggestions, PlanItem } from "@/types/api";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));
vi.mock("@/lib/api/action-plans", () => ({ streamActionPlanSuggestions: vi.fn() }));

const addSuggested = vi.fn();
const toggleSaved = vi.fn();
const GAP_ORDER = ["sql", "dashboarding", "statistics"];
const ALL_ENTRIES = { steps: ["sql-course", "sql-project", "dashboard-course"], alongside: ["data-club"] };

function mockPlan(items: PlanItem[] = [], pending: string[] = []) {
  vi.mocked(usePlan).mockReturnValue({
    family: "data_analyst", status: "ready", resources, items,
    saved: new Map(items.map((item) => [item.resource_id, item])), pending: new Set(pending),
    justCompleted: null, justSaved: null, setStatus: vi.fn(), remove: vi.fn(), toggleSaved, addSuggested,
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
  vi.mocked(streamActionPlanSuggestions).mockResolvedValue(response);
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
    addSuggested.mockResolvedValue(true);
    mockPlan();
  });

  it("asks for the role's plan and shows that it is working", async () => {
    vi.mocked(streamActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    renderPanel();
    expect(await screen.findByRole("list", { name: "Plan building steps" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Reading your gaps");
    expect(streamActionPlanSuggestions).toHaveBeenCalledWith("data_analyst", expect.any(Function),
      { signal: expect.any(AbortSignal) });
  });

  it("shows each stage as the stream reports it, then the plan", async () => {
    let finish: (value: ActionPlanSuggestions) => void = () => {};
    vi.mocked(streamActionPlanSuggestions).mockImplementation((_family, onStage) => new Promise((resolve) => {
      onStage({ type: "stage", stage: "gaps", gaps: [{ skill_id: "sql", skill_name: "SQL" }] });
      onStage({ type: "stage", stage: "candidates", counts: { project: 2 }, samples: [{ title: "SQL project", type: "project" }] });
      onStage({ type: "stage", stage: "agent" });
      finish = resolve;
    }));
    renderPanel();
    expect(await screen.findByRole("status")).toHaveTextContent("Your mentor is choosing and ordering the steps");
    finish(suggestions());
    expect(await screen.findByRole("heading", { name: "SQL first, then dashboards" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Plan building steps" })).not.toBeInTheDocument();
  });

  it("shows the plan in order, with each mentor reason and the alongside items", async () => {
    await renderReady();
    const steps = within(screen.getByRole("list", { name: "Main path, in order" })).getAllByRole("listitem");
    expect(steps.map((step) => within(step).getByText(/^Step \d:/, { exact: false }).parentElement?.textContent)).toEqual([
      "Step 1: SQL for Data Analysis", "Step 2: Analyze a public dataset with SQL", "Step 3: Building Dashboards",
    ]);
    expect(within(steps[0]).getByText("Learn joins and aggregates before you query real data.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Alongside" })).getByText("Data Science Club")).toBeInTheDocument();
  });

  it("shows no reason box for a step without a mentor reason, so its skills appear once", async () => {
    // Review on PR #58: a rule plan or filled-in step used to repeat "Closes …" in the reason box.
    const [first, ...rest] = actionPlanSuggestions.plans[0].steps;
    await renderReady(suggestions({ source: "rules" }, { steps: [{ ...first, reason: "" }, ...rest] }));
    const step = card("SQL for Data Analysis");
    expect(within(step).getAllByText(/Closes/)).toHaveLength(1);
    expect(within(step).queryByText("Learn joins and aggregates before you query real data.")).not.toBeInTheDocument();
    expect(within(card("Analyze a public dataset with SQL"))
      .getByText("Publish an analysis with your queries to prove SQL.")).toBeInTheDocument();
  });

  it("shows each card's type as a tag and its details as time · cost · level, skipping missing ones", async () => {
    // Review on PR #58: every type in the same order, so cards compare at a glance.
    await renderReady();
    const details = (title: string) => [...card(title).querySelectorAll("p")].map((line) => line.textContent)
      .find((text) => text?.includes(" · "));
    expect(details("SQL for Data Analysis")).toBe("Example Courses · 6 weeks · Free");
    expect(details("Analyze a public dataset with SQL")).toBe("CareerGPS · 12 h · Beginner");
    expect(details("Data Science Club")).toBe("Example University · Weekly · Free");
    expect(within(card("SQL for Data Analysis")).getByText("6 weeks")).toHaveClass("font-mono");
    // Numbers are monospaced; words such as "Free" or "Weekly" are not.
    expect(within(card("SQL for Data Analysis")).getByText("Free")).not.toHaveClass("font-mono");
    expect(within(card("Data Science Club")).getByText("Weekly")).not.toHaveClass("font-mono");
    expect(within(card("Analyze a public dataset with SQL")).getByText("Project")).toBeInTheDocument();
  });

  it("shows step 1 as a full card and the rest as one line each, with their reasons behind Why", async () => {
    // Review on PR #58: less before step 1, and nothing lost (explainability is a project requirement).
    await renderReady();
    expect(within(card("SQL for Data Analysis")).getByText("Learn joins and aggregates before you query real data."))
      .toBeVisible();
    expect(within(card("SQL for Data Analysis")).queryByRole("button", { name: /^Why/ })).not.toBeInTheDocument();

    const second = card("Analyze a public dataset with SQL");
    const why = within(second).getByRole("button", { name: "Why: Analyze a public dataset with SQL" });
    const reason = within(second).getByText("Publish an analysis with your queries to prove SQL.");
    expect(why).toHaveAttribute("aria-expanded", "false");
    expect(reason).not.toBeVisible();
    await userEvent.click(why);
    expect(why).toHaveAttribute("aria-expanded", "true");
    expect(reason).toBeVisible();
    expect(within(card("Data Science Club")).getByRole("button", { name: /^Why/ })).toBeInTheDocument();
  });

  it("lists the alongside items after the main path", async () => {
    await renderReady();
    const main = screen.getByRole("list", { name: "Main path, in order" });
    const alongside = screen.getByRole("list", { name: "Alongside" });
    expect(main.compareDocumentPosition(alongside) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps lime for step 1 only", async () => {
    // Review on PR #58: the design system saves lime for the one next step.
    mockPlan([planItem("sql-project")]);
    await renderReady();
    const limed = [...document.querySelectorAll(".bg-accent")];
    expect(limed).toHaveLength(1);
    expect(card("SQL for Data Analysis")).toContainElement(limed[0] as HTMLElement);
    expect(within(card("Analyze a public dataset with SQL")).getByRole("button", { name: /In your plan/ }))
      .not.toHaveClass("bg-accent");
  });

  describe("skills highlight", () => {
    it("lists the covered skills in gap order and marks the top gap, without step counts", async () => {
      await renderReady();
      expect(skillChips()).toEqual(["1SQL · top gap", "2Dashboard development"]);
    });

    it("marks a skill only the alongside items cover", async () => {
      await renderReady(suggestions({}, { steps: actionPlanSuggestions.plans[0].steps.slice(0, 2) }));
      expect(skillChips()).toEqual(["1SQL · top gap", "2Dashboard development · alongside"]);
    });

    it("shows a gap no resource closes as not covered yet", async () => {
      await renderReady(suggestions({ uncovered_skill_ids: ["statistics"] }));
      expect(skillChips()).toContain("3Statistics · not covered yet");
    });

    it("counts covered gaps out of all the student's gaps, like the Gaps page", async () => {
      // GAP_ORDER has 3 gaps; the plan covers the top 2.
      await renderReady();
      expect(screen.getByText("2 of 3")).toBeInTheDocument();
      expect(screen.getByText("gaps covered")).toBeInTheDocument();
    });

    it("says the plan focuses on the biggest gaps and points to the rest", async () => {
      await renderReady();
      expect(screen.getByText(/This plan focuses on your 2 biggest gaps\. The other 1 is on/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Gaps page" })).toHaveAttribute("href", "/gaps");
    });

    it("has no such note when the plan targets every gap", async () => {
      await renderReady(suggestions({ uncovered_skill_ids: ["statistics"] }));
      expect(screen.queryByText(/This plan focuses on/)).not.toBeInTheDocument();
    });

    it("puts gaps covered, steps and project hours on one line", async () => {
      await renderReady();
      expect(screen.getByText("≈ 12 h").closest("p")).toHaveTextContent("2 of 3 gaps covered · 3 steps + 1 alongside · ≈ 12 h of project work");
      expect(screen.getByText("3 steps")).toHaveClass("font-mono");
    });

    it("leaves out the hours when no project has an estimate", async () => {
      await renderReady(suggestions({}, { project_hours: null }));
      expect(screen.queryByText(/of project work/)).not.toBeInTheDocument();
    });
  });

  describe("adding", () => {
    it("saves a single card like any resource, so it slots in by gap", async () => {
      // Review on PR #58: only "Add all" sets an order; one card must not jump ahead of top-gap steps.
      await renderReady();
      await userEvent.click(within(card("Analyze a public dataset with SQL")).getByRole("button", { name: /Add to plan/ }));
      expect(toggleSaved).toHaveBeenCalledWith("sql-project");
      expect(addSuggested).not.toHaveBeenCalled();
    });

    it("shows a saved card as in your plan, and pressing it again removes it", async () => {
      mockPlan([planItem("sql-project")]);
      await renderReady();
      const button = within(card("Analyze a public dataset with SQL")).getByRole("button", { name: /In your plan/ });
      expect(button).toHaveAttribute("aria-pressed", "true");
      await userEvent.click(button);
      expect(toggleSaved).toHaveBeenCalledWith("sql-project");
    });

    it("disables a card's button while it saves", async () => {
      mockPlan([], ["sql-course"]);
      await renderReady();
      expect(within(card("SQL for Data Analysis")).getByRole("button", { name: /Add to plan/ })).toBeDisabled();
    });

    it("adds the whole plan in one call, steps in order, then closes", async () => {
      const onClose = await renderReady();
      await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
      expect(addSuggested).toHaveBeenCalledWith(ALL_ENTRIES);
      expect(onClose).toHaveBeenCalledOnce();
    });

    it("stays open when adding fails", async () => {
      addSuggested.mockResolvedValue(false);
      const onClose = await renderReady();
      await userEvent.click(screen.getByRole("button", { name: "Add all to my plan" }));
      expect(onClose).not.toHaveBeenCalled();
    });

    it("says all in your plan once every card is saved", async () => {
      mockPlan([...ALL_ENTRIES.steps, ...ALL_ENTRIES.alongside].map((id) => planItem(id)));
      await renderReady();
      expect(screen.getByRole("button", { name: "All in your plan" })).toBeDisabled();
    });
  });

  it("shows the backend's message and asks again on Try again", async () => {
    vi.mocked(streamActionPlanSuggestions)
      .mockRejectedValueOnce(new ApiError(409, "failed", "The skill gap analysis has not finished yet"))
      .mockResolvedValueOnce(suggestions());
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("The skill gap analysis has not finished yet");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "SQL first, then dashboards" })).toBeInTheDocument();
    expect(streamActionPlanSuggestions).toHaveBeenCalledTimes(2);
  });

  it("closes from Cancel while loading and from Dismiss when ready", async () => {
    vi.mocked(streamActionPlanSuggestions).mockReturnValue(new Promise(() => {}));
    const onCancel = vi.fn();
    const { unmount } = render(<SuggestedPlan family="data_analyst" gapOrder={GAP_ORDER} onClose={onCancel} />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
    unmount();

    const onClose = await renderReady();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(addSuggested).not.toHaveBeenCalled();
  });

  it("notes a rule plan in the footer", async () => {
    await renderReady(suggestions({ source: "rules" }));
    expect(screen.getByText("Built from your gap ranking.")).toBeInTheDocument();
  });
});
