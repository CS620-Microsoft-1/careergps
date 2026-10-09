import { Check, Circle, LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AgentStatus, AgentStep } from "@/types/agents";

const STATUS: Record<AgentStatus, { label: string; icon: typeof Check; className: string }> = {
  complete: { label: "Complete", icon: Check, className: "bg-success-soft text-success" },
  running: { label: "Running", icon: LoaderCircle, className: "bg-accent text-primary [&>svg]:animate-spin" },
  waiting: { label: "Waiting", icon: Circle, className: "border bg-card text-muted-foreground" },
};

/** Vertical list of analysis agents, joined by a connecting line, with their status. */
export function AgentPipeline({ steps }: { steps: AgentStep[] }) {
  return (
    <ol className="grid gap-3.5">
      {steps.map((step, i) => {
        const status = STATUS[step.status];
        const Icon = status.icon;
        return (
          <li key={step.name} className="relative flex items-start gap-3">
            {i < steps.length - 1 && (
              <span aria-hidden className="absolute top-6.5 -bottom-3 left-[0.6875rem] w-px bg-border" />
            )}
            <span
              className={cn("grid size-5.5 shrink-0 place-items-center rounded-full", status.className)}
            >
              <Icon aria-hidden className="size-3" />
            </span>
            <div className="min-w-0">
              <p className="text-control font-semibold">
                {step.name}
                <span className="sr-only"> — {status.label}</span>
              </p>
              <p className="text-xs text-muted-foreground">{status.label}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
