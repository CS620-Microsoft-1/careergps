import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description?: string;
  /** Optional call to action, e.g. a Button linking to onboarding. */
  action?: React.ReactNode;
  className?: string;
};

/** Placeholder shown wherever analysis results will appear. */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "grid justify-items-center gap-1 px-4 py-8 text-center",
        className,
      )}
    >
      <span className="mb-2 grid size-10 place-items-center rounded-full bg-accent text-primary">
        <Icon aria-hidden className="size-5" />
      </span>
      <p className="font-semibold">{title}</p>
      {description && (
        <p className="max-w-80 text-control text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
