import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "CareerGPS",
    template: "%s · CareerGPS",
  },
  description:
    "Understand where you stand, what employers are looking for, and what to do next.",
};

// width=device-width / initial-scale=1 are Next.js defaults. viewport-fit=cover
// lets fixed elements use env(safe-area-inset-*) on notched phones.
export const viewport: Viewport = {
  themeColor: "#f6f8f7",
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="min-h-full">
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
