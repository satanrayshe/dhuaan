import type { Metadata } from "next";
import { Suspense } from "react";
import { SchoolsView } from "@/components/dhuaan/schools-view";

export const metadata: Metadata = { title: "Schools" };

export default function SchoolsPage() {
  return (
    <Suspense fallback={null}>
      <SchoolsView />
    </Suspense>
  );
}
