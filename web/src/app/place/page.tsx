import type { Metadata } from "next";
import { Suspense } from "react";
import { PlaceView } from "@/components/dhuaan/place-view";

export const metadata: Metadata = { title: "Place forecast" };

export default function PlacePage() {
  return (
    <Suspense fallback={null}>
      <PlaceView />
    </Suspense>
  );
}
