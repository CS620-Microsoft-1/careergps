"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeftRight, ChevronDown, LogOut, User } from "lucide-react";

import { BackendStatus } from "@/components/layout/backend-status";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PLACEHOLDER_USER } from "@/lib/placeholder-user";
import { getSupabase } from "@/lib/supabase/client";

type MenuUser = { name: string; initials: string; detail: string };

export function UserMenu() {
  const router = useRouter();
  const [user, setUser] = useState<MenuUser>(PLACEHOLDER_USER);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSupabase()
      .auth.getUser()
      .then(({ data }) => {
        if (cancelled || !data.user) return;
        const address = data.user.email ?? "";
        // Sign-up asks only for email and password, so the email stands in for a name.
        setUser({
          name: address.split("@")[0] || PLACEHOLDER_USER.name,
          initials: address[0]?.toUpperCase() || PLACEHOLDER_USER.initials,
          detail: address.split("@")[1] ?? "",
        });
        setEmail(address || null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function signOut() {
    // Local scope: sign out this browser only, not the user's other devices.
    await getSupabase().auth.signOut({ scope: "local" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="ml-1.5 flex items-center gap-2.5 rounded-lg py-1 pr-2 pl-1 text-left transition-colors outline-none hover:bg-background focus-visible:ring-2 focus-visible:ring-primary aria-expanded:bg-background">
        <Avatar>
          <AvatarFallback>{user.initials}</AvatarFallback>
        </Avatar>
        <span className="hidden leading-tight sm:block">
          <b className="block text-control font-semibold">{user.name}</b>
          <span className="text-xs text-muted-foreground">{user.detail}</span>
        </span>
        <ChevronDown aria-hidden className="size-4 text-muted-foreground" />
        <span className="sr-only">Open account menu</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-52">
        <DropdownMenuLabel className="grid gap-1.5 text-xs font-normal text-muted-foreground">
          {email ?? "Signed in"}
          <BackendStatus interactive={false} />
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/profile">
            <User /> My Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={signOut}>
          <ArrowLeftRight /> Switch account
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
