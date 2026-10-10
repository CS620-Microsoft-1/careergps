"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

import { Logo } from "@/components/common/logo";
import { Progress } from "@/components/ui/progress";
import { NAV_ITEMS, isActive } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Desktop navigation (lg+). Pinned to the viewport while the page scrolls. */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-dvh flex-col gap-6 overflow-y-auto border-r bg-sidebar px-3 py-5 lg:flex">
      <Link href="/dashboard" className="rounded-lg px-2">
        <Logo />
      </Link>

      <nav aria-label="Main" className="grid gap-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-9.5 items-center gap-2.5 rounded-lg px-2.5 font-medium text-sidebar-foreground transition-colors hover:bg-background",
                active && "bg-sidebar-accent font-semibold text-sidebar-accent-foreground hover:bg-sidebar-accent",
              )}
            >
              <Icon
                aria-hidden
                className={cn("size-4.5", active ? "text-primary" : "text-muted-foreground")}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-xl border p-3.5">
        <div className="mb-2 flex justify-between text-control text-ink-2">
          <span>Profile strength</span>
          <b className="font-semibold text-foreground">—</b>
        </div>
        <Progress value={0} aria-label="Profile strength" />
        <p className="mt-2.5 mb-1.5 text-xs text-muted-foreground">
          Upload your résumé to measure your profile strength.
        </p>
        <Link
          href="/onboarding"
          className="inline-flex items-center gap-0.5 text-control font-semibold text-primary hover:underline"
        >
          Complete profile <ChevronRight aria-hidden className="size-3.5" />
        </Link>
      </div>
    </aside>
  );
}
