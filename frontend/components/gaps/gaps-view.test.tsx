import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GapsView } from "@/components/gaps/gaps-view";
import { usePlan } from "@/components/plan/plan-provider";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { resources, resume, run, user } from "@/test/fixtures";

vi.mock("@/components/plan/plan-provider", () => ({ usePlan: vi.fn() }));
vi.mock("@/components/skill-gaps/skill-gap-provider", () => ({ useSkillGapAnalysis: vi.fn() }));

type Analysis = ReturnType<typeof useSkillGapAnalysis>;

function mockAnalysis(overrides: Partial<Analysis> = {}) {
  vi.mocked(useSkillGapAnalysis).mockReturnValue({
    loaded: true, family: "data_analyst", run, submitting: false, restoring: false, elapsed: 0,
    snapshot: { user_id: user.id, resume_id: resume.id, filename: resume.original_filename,
      confirmed_at: resume.created_at, job_family: "data_analyst" },
    analyze: vi.fn(), changeFamily: vi.fn(),
    ...overrides,
  });
}

/** The panel a gap card's toggle opens and closes. */
const panelOf = (toggle: HTMLElement) => document.getElementById(toggle.getAttribute("aria-controls")!)!;

describe("GapsView", () => {
  beforeEach(() => {
    vi.mocked(usePlan).mockReturnValue({
      family: "data_analyst", status: "ready", resources, items: [], saved: new Map(), pending: new Set(),
      justCompleted: null, justSaved: null, setStatus: vi.fn(), remove: vi.fn(), toggleSaved: vi.fn(),
    });
    mockAnalysis();
  });

  it("ranks the gaps and lists strengths and skills to review", () => {
    render(<GapsView />);
    expect(screen.getByRole("heading", { level: 1, name: "2 gaps to close" })).toBeInTheDocument();
    expect(screen.getByText("Analytical scripting")).toBeInTheDocument();
    expect(screen.getByText("Statistics")).toBeInTheDocument();
    expect(screen.getByText("42% match")).toBeInTheDocument();
  });

  it("opens the biggest gap and keeps the rest closed", () => {
    render(<GapsView />);
    const first = screen.getByRole("button", { name: "Hide ways to close SQL" });
    const second = screen.getByRole("button", { name: "Show ways to close Dashboard development" });
    expect(first).toHaveAttribute("aria-expanded", "true");
    expect(panelOf(first)).toHaveAttribute("data-open", "true");
    expect(second).toHaveAttribute("aria-expanded", "false");
    // Closed panels stay mounted so they can animate, but out of reach until opened.
    expect(panelOf(second)).toHaveAttribute("data-open", "false");
    expect(panelOf(second)).toHaveAttribute("inert");
  });

  it("opens a closed gap from its toggle", async () => {
    render(<GapsView />);
    await userEvent.click(screen.getByRole("button", { name: "Show ways to close Dashboard development" }));
    const toggle = screen.getByRole("button", { name: "Hide ways to close Dashboard development" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(panelOf(toggle)).not.toHaveAttribute("inert");
  });

  it("lists the resources for an open gap", () => {
    render(<GapsView />);
    const panel = panelOf(screen.getByRole("button", { name: "Hide ways to close SQL" }));
    expect(panel).toHaveTextContent("SQL for Data Analysis");
    expect(panel).toHaveTextContent("Browse all 2 resources for this skill");
  });

  it("shows the analysis gate until the analysis is ready", () => {
    mockAnalysis({ loaded: false, run: null, snapshot: null });
    render(<GapsView />);
    expect(screen.getByRole("heading", { level: 1, name: "Your gaps" })).toBeInTheDocument();
    expect(screen.getByText("Loading your route…")).toBeInTheDocument();
  });
});
