import {
  BriefcaseBusiness,
  ChartColumn,
  ClipboardList,
  LayoutGrid,
  Target,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

/** Main app navigation, shared by the desktop sidebar and the mobile nav. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/market", label: "Career Analysis", icon: Target },
  { href: "/gaps", label: "Skill Gaps", icon: ChartColumn },
  { href: "/opportunities", label: "Resources", icon: BriefcaseBusiness },
  { href: "/roadmap", label: "Action Plan", icon: ClipboardList },
];

export function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
