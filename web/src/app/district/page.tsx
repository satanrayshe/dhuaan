import type { Metadata } from "next";
import { DistrictView } from "@/components/dhuaan/district-view";

export const metadata: Metadata = { title: "District" };

export default function DistrictPage() {
  return <DistrictView />;
}
