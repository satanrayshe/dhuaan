import type { Metadata } from "next";
import { BacktestView } from "@/components/dhuaan/backtest-view";

export const metadata: Metadata = { title: "Backtest" };

export default function BacktestPage() {
  return <BacktestView />;
}
