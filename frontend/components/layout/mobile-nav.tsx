"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS, isActive } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Horizontal, scrollable page links shown below lg in place of the sidebar. */
export function MobileNav() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);

  // On narrow phones the active link can sit past the edge; bring it into view.
  useEffect(() => {
    navRef.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pathname]);

  return (
    <nav
      ref={navRef}
      aria-label="Main"
      className="flex gap-1 overflow-x-auto border-b bg-card px-4 py-2 [scrollbar-width:none] sm:px-8 lg:hidden"
    >
      {NAV_ITEMS.map(({ href, label }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-8 shrink-0 items-center rounded-lg px-2.5 text-control font-semibold whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground",
              active && "bg-accent text-accent-foreground hover:text-accent-foreground",
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
