import type { Metadata } from "next";
import { HowView } from "@/components/dhuaan/how-view";

export const metadata: Metadata = { title: "How it works" };

export default function HowPage() {
  return <HowView />;
}
