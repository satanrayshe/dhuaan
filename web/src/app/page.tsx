import { Suspense } from "react";
import { MapApp } from "@/components/dhuaan/map-app";

export default function Home() {
  return (
    <Suspense fallback={<div className="h-[calc(100dvh-3.5rem)] bg-surface-map" />}>
      <MapApp />
    </Suspense>
  );
}
