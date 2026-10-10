"use client";

import Link from "next/link";
import { ArrowLeftRight, ChevronDown, LogOut, User } from "lucide-react";

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

export function UserMenu() {
  const user = PLACEHOLDER_USER;

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
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Preview mode · no account yet
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/profile">
            <User /> My Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/login">
            <ArrowLeftRight /> Switch account
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/login">
            <LogOut /> Sign out
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
