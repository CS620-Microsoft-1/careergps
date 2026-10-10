import Link from "next/link";
import { Bell, Search, Settings } from "lucide-react";

import { ComingSoon } from "@/components/common/coming-soon";
import { Logo } from "@/components/common/logo";
import { MobileNav } from "@/components/layout/mobile-nav";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";

/** Sticky header: search, notifications, settings, account; mobile nav below lg. */
export function Topbar() {
  return (
    <header className="sticky top-0 z-20 bg-card/90 pt-[env(safe-area-inset-top)] backdrop-blur-sm">
      <div className="flex h-15 items-center gap-1.5 border-b px-4 sm:px-8">
        <Link href="/dashboard" className="mr-2 rounded-lg lg:hidden">
          <Logo nameClassName="max-sm:sr-only" />
        </Link>
        <ComingSoon className="mr-auto">
          <span className="flex h-9 items-center gap-2 px-1 text-control text-muted-foreground">
            <Search aria-hidden className="size-4.5" />
            <span className="hidden sm:inline">Search CareerGPS</span>
          </span>
        </ComingSoon>
        <ComingSoon>
          <Button variant="ghost" size="icon" disabled className="text-ink-2 disabled:opacity-100" aria-label="Notifications">
            <Bell />
          </Button>
        </ComingSoon>
        <ComingSoon>
          <Button variant="ghost" size="icon" disabled className="text-ink-2 disabled:opacity-100" aria-label="Settings">
            <Settings />
          </Button>
        </ComingSoon>
        <UserMenu />
      </div>
      <MobileNav />
    </header>
  );
}
