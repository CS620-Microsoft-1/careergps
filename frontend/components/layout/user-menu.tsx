"use client";

import Link from "next/link";
import { ArrowLeftRight, ChevronDown, LogOut, User } from "lucide-react";

import { BackendStatus } from "@/components/layout/backend-status";
import { useSkillGapAnalysis } from "@/components/skill-gaps/skill-gap-provider";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { getResumeProfile } from "@/lib/resume-profile";

export function UserMenu() {
  const { snapshot, loaded } = useSkillGapAnalysis();
  const user = getResumeProfile(snapshot);
  const name = loaded ? user.name : "Loading profile…";
  const detail = loaded ? user.subtitle : "Your reviewed résumé";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="ml-1.5 flex items-center gap-2.5 rounded-lg py-1 pr-2 pl-1 text-left transition-colors outline-none hover:bg-background focus-visible:ring-2 focus-visible:ring-primary aria-expanded:bg-background">
        <Avatar>
          <AvatarFallback>{user.initials}</AvatarFallback>
        </Avatar>
        <span className="hidden min-w-0 max-w-44 leading-tight sm:block">
          <b title={name} className="block truncate text-control font-semibold">{name}</b>
          <span title={detail} className="block truncate text-xs text-muted-foreground">{detail}</span>
        </span>
        <ChevronDown aria-hidden className="size-4 text-muted-foreground" />
        <span className="sr-only">Open account menu</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-52">
        <DropdownMenuLabel className="grid gap-1.5 text-xs font-normal text-muted-foreground">
          {snapshot ? "Reviewed résumé · local preview" : "Local preview · résumé not confirmed"}
          <BackendStatus interactive={false} />
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
