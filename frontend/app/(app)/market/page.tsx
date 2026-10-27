import type { Metadata } from "next";
import { MarketWorkspace } from "@/components/market/market-workspace";

export const metadata: Metadata = { title: "Career Analysis" };

export default function MarketPage() {
  return <MarketWorkspace />;
}
