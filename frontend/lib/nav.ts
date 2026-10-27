import { BookOpen, Flag, House, Layers, Route, type LucideIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

/** Main app navigation, shared by the nav bar and its phone menu. Profile sits apart, on the right. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", icon: House },
  { href: "/gaps", label: "Gaps", icon: Layers },
  { href: "/resources", label: "Resources", icon: BookOpen },
  { href: "/plan", label: "Action plan", icon: Route },
  { href: "/destinations", label: "Destinations", icon: Flag },
];

export function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}
