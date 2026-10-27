import type { Metadata, Viewport } from "next";
import { DM_Mono, Nunito } from "next/font/google";
import { SupabaseInit } from "@/components/auth/supabase-init";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const nunito = Nunito({
  variable: "--font-nunito",
  subsets: ["latin", "latin-ext"],
});

const dmMono = DM_Mono({
  variable: "--font-dm-mono",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: {
    default: "CareerGPS",
    template: "%s · CareerGPS",
  },
  description:
    "Where you are, where you’re going, and your next turn.",
};

// width=device-width / initial-scale=1 are Next.js defaults. viewport-fit=cover
// lets fixed elements use env(safe-area-inset-*) on notched phones.
export const viewport: Viewport = {
  themeColor: "#f7f3ef",
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${nunito.variable} ${dmMono.variable} h-full`}>
      <body className="min-h-full">
        <SupabaseInit />
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
