"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { ArrowLeftIcon, Share2Icon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useFires, useGrid, useMeta, usePlace, useReceptors } from "@/lib/data";
import { useI18n } from "@/lib/i18n";
import { msToOffset, toMs } from "@/lib/time";
import { AskPanel } from "./ask-panel";
import { AqNowChip, ArrivalPeak, PlaceCardSkeleton } from "./place-card";
import { setSearchOpen } from "./place-search";
import { AttributionBars, ForecastChart } from "./forecast-chart";
import { SampleBadge } from "./top-bar";

const SmokeMap = dynamic(() => import("./smoke-map"), { ssr: false, loading: () => <div className="h-full bg-surface-map" /> });

export function PlaceView() {
  const params = useSearchParams();
  const id = params.get("id");
  const res = usePlace(id);
  const meta = useMeta();
  const grid = useGrid();
  const fires = useFires();
  const idx = useReceptors();
  const { t, kind } = useI18n();

  const peakHour = useMemo(() => {
    if (res.status !== "ready") return 0;
    return Math.round(msToOffset(res.data.t0_utc, toMs(res.data.peak_utc)));
  }, [res]);

  if (!id)
    return (
      <div className="mx-auto max-w-xl px-5 py-20 text-center">
        <p className="text-muted-foreground">{t("place.pick")}</p>
        <Button className="mt-4" onClick={() => setSearchOpen(true)}>
          {t("search.placeholder")}
        </Button>
      </div>
    );
  if (res.status === "loading" || res.status === "idle")
    return (
      <div className="mx-auto w-full max-w-6xl">
        <PlaceCardSkeleton />
      </div>
    );
  if (res.status !== "ready")
    return (
      <div className="mx-auto max-w-xl px-5 py-20 text-center">
        <p className="text-muted-foreground">{t("place.notFound")}</p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/">{t("place.back")}</Link>
        </Button>
      </div>
    );

  const place = res.data;
  const share = () => {
    const url = window.location.href;
    if (navigator.share) navigator.share({ title: `Dhuaan · ${place.name}`, url }).catch(() => {});
    else navigator.clipboard?.writeText(url).then(() => toast(t("place.copied")));
  };

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:py-12">
      <div className="flex items-center justify-between gap-3">
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href={`/?place=${encodeURIComponent(place.id)}`}>
            <ArrowLeftIcon aria-hidden /> {t("place.back")}
          </Link>
        </Button>
        <div className="flex items-center gap-2">
          <SampleBadge className="sm:hidden" />
          <Button variant="outline" size="sm" onClick={share}>
            <Share2Icon aria-hidden /> {t("place.share")}
          </Button>
        </div>
      </div>

      <header className="mt-6">
        <p className="label-mono">{kind(place.kind)}</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">{place.name}</h1>
        <p className="mt-2 text-muted-foreground">
          {place.district}, {place.state}
        </p>
      </header>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-12">
        <div className="min-w-0 space-y-10">
          <ArrivalPeak place={place} meta={meta.data} large />
          <ForecastChart place={place} meta={meta.data} height={280} />
          <div className="grid gap-10 md:grid-cols-2">
            <AttributionBars place={place} />
            <div className="space-y-3">
              <AqNowChip place={place} />
            </div>
          </div>
        </div>
        <aside className="min-w-0 space-y-8">
          <div className="h-64 overflow-hidden rounded-lg border border-border">
            {meta.data && (
              <SmokeMap
                className="h-full"
                ariaLabel={t("map.label")}
                t0={meta.data.t0_utc}
                grid={grid.data}
                fires={fires.data}
                places={idx.data?.places}
                layers={{ fires: true, missed: true, trails: false, field: true, places: true }}
                selectedPlaceId={place.id}
                staticHour={peakHour}
                flyTo={{ lon: place.lon, lat: place.lat, zoom: 7, key: place.id }}
                reducedMotion
                initialZoom={6}
              />
            )}
          </div>
          <AskPanel placeId={place.id} placeName={place.name} />
        </aside>
      </div>
    </div>
  );
}
