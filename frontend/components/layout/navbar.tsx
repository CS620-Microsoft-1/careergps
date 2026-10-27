"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Check, ChevronDown, LogOut, Menu, Plus, User } from "lucide-react";

import { ROLE_NAMES } from "@/components/career/route-parts";
import { ADD_DESTINATION_HREF, FAMILIES, useDestinationRuns } from "@/components/destinations/use-destination-runs";
import { useAccount } from "@/components/layout/account-provider";
import { useSwitchRoute } from "@/components/layout/use-switch-route";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { NAV_ITEMS, isActive } from "@/lib/nav";
import { getSupabase } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/** Sticky top bar: wordmark, destination switcher, page links (a menu below lg) and the profile menu. */
export function Navbar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-card/95 pt-[env(safe-area-inset-top)] shadow-card backdrop-blur-sm">
      <div className="mx-auto flex max-w-300 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-6 lg:flex-nowrap lg:gap-x-3">
        <Link href="/dashboard" className="shrink-0 rounded-md text-[1.375rem] leading-8 font-extrabold tracking-[-0.01em]">
          CareerGPS
        </Link>
        <RouteSwitcher />
        <nav aria-label="Main" className="hidden shrink-0 items-center gap-0.5 lg:flex">
          {NAV_ITEMS.map((item) => <NavLink key={item.href} {...item} active={isActive(pathname, item.href)} />)}
        </nav>
        <div className="flex-1" />
        <ProfileMenu active={isActive(pathname, "/profile")} />
        <PhoneMenu pathname={pathname} />
      </div>
    </header>
  );
}

/** Extra props come from SheetClose asChild, which closes the phone menu on click. */
function NavLink({ href, label, icon: Icon, active, ...props }: (typeof NAV_ITEMS)[number] & {
  active: boolean;
} & Omit<React.ComponentProps<typeof Link>, "href">) {
  return (
    <Link {...props} href={href} aria-current={active ? "page" : undefined}
      className={cn("inline-flex h-10 items-center gap-2 rounded-full px-3 text-control font-semibold text-muted-foreground transition-colors hover:text-foreground",
        active && "bg-accent font-bold text-accent-foreground")}>
      <Icon aria-hidden className="size-4.5" />{label}
    </Link>
  );
}

function RouteSwitcher() {
  const { snapshot, loaded } = useSkillGapAnalysis();
  const { family, locked, switchTo } = useSwitchRoute();
  const explored = useDestinationRuns().families;
  if (!loaded || !snapshot) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger disabled={locked}
        aria-label={`Current destination: ${ROLE_NAMES[family]}, ${snapshot.filename}. Switch destination`}
        className="inline-flex h-10 max-w-full min-w-0 items-center gap-2 rounded-full border border-border bg-card pr-3 pl-3.5 text-left outline-none hover:bg-background focus-visible:ring-3 focus-visible:ring-ring/30 disabled:opacity-60">
        <span className="font-bold whitespace-nowrap">{ROLE_NAMES[family]}</span>
        <span className="hidden max-w-40 min-w-0 truncate text-sm text-muted-foreground sm:inline lg:max-w-28 xl:max-w-40">· {snapshot.filename}</span>
        <ChevronDown aria-hidden className="size-4.5 shrink-0" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-60">
        <DropdownMenuLabel className="eyebrow">Destination</DropdownMenuLabel>
        {explored.map((key) => (
          <DropdownMenuItem key={key} onSelect={() => void switchTo(key)}>
            <Check aria-hidden className={cn(key !== family && "invisible")} />{ROLE_NAMES[key]}
          </DropdownMenuItem>
        ))}
        {explored.length < FAMILIES.length && (
          <DropdownMenuItem asChild><Link href={ADD_DESTINATION_HREF}><Plus />Add a destination</Link></DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link href="/destinations">Compare destinations</Link></DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ProfileMenu({ active }: { active: boolean }) {
  const router = useRouter();
  const { initials, email, displayName } = useAccount();
  async function signOut() {
    // Local scope: sign out this browser only, not the user's other devices.
    await getSupabase().auth.signOut({ scope: "local" });
    router.replace("/login");
    router.refresh();
  }
  const avatar = (size: string) => (
    <span aria-hidden className={cn("grid shrink-0 place-items-center rounded-full bg-tint-blue text-sm font-bold text-foreground", size)}>{initials}</span>
  );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label="Open profile menu"
        className={cn("inline-flex size-11 shrink-0 items-center justify-center rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
          active && "bg-accent")}>
        {avatar("size-9")}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-64">
        <DropdownMenuLabel className="flex items-center gap-3 py-2 font-normal">
          {avatar("size-10")}
          <span className="grid min-w-0">
            <span className="truncate font-bold text-foreground">{displayName || "Signed in"}</span>
            {email && <span className="truncate text-xs text-muted-foreground">{email}</span>}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link href="/profile"><User />Your profile</Link></DropdownMenuItem>
        <DropdownMenuItem onSelect={signOut}><LogOut />Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function PhoneMenu({ pathname }: { pathname: string }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="icon" className="lg:hidden" aria-label="Open menu"><Menu /></Button>
      </SheetTrigger>
      <SheetContent side="right" className="gap-1 p-4 pt-16">
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <nav aria-label="Main" className="grid gap-1">
          {NAV_ITEMS.map((item) => (
            <SheetClose key={item.href} asChild>
              <NavLink {...item} active={isActive(pathname, item.href)} />
            </SheetClose>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
