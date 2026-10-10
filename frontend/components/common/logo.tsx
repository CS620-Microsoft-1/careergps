import { Target } from "lucide-react";

import { cn } from "@/lib/utils";

type LogoProps = {
  /** "light" for dark backgrounds (auth panel), "default" elsewhere. */
  tone?: "default" | "light";
  className?: string;
  /** Extra classes for the "CareerGPS" wordmark, e.g. to hide it on small screens. */
  nameClassName?: string;
};

export function Logo({ tone = "default", className, nameClassName }: LogoProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 text-lg font-bold tracking-[-0.01em]",
        tone === "light" ? "text-deep-foreground" : "text-foreground",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "grid size-8 place-items-center rounded-[0.5625rem]",
          tone === "light"
            ? "bg-white/12"
            : "bg-primary text-primary-foreground",
        )}
      >
        <Target className="size-4.5" />
      </span>
      <span className={nameClassName}>CareerGPS</span>
    </div>
  );
}
