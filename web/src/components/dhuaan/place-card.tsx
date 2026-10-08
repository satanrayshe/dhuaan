"use client";

import Link from "next/link";
import { ExternalLinkIcon, Share2Icon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { naqiFromPm25 } from "@/lib/colors";
import { useMeta, usePlace } from "@/lib/data";
import { useI18n } from "@/lib/i18n";
import { useHour } from "@/lib/playback";
import { ageLabel, istDayTime, istTime, toMs } from "@/lib/time";
import type { Meta, PlaceDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AskPanel } from "./ask-panel";
import { NaqiChip, SectionLabel } from "./bits";
import { AttributionBars, ForecastChart } from "./forecast-chart";

function sharePlace(id: string, name: string, copiedMsg: string) {
  const url = `${window.location.origin}/place/?id=${encodeURIComponent(id)}`;
  if (navigator.share) {
    navigator.share({ title: `Dhuaan · ${name}`, url }).catch(() => {});
  } else {
    navigator.clipboard?.writeText(url).then(() => toast(copiedMsg));
  }
}

export function ArrivalPeak({ place, meta, large = false }: { place: PlaceDetail; meta?: Meta; large?: boolean }) {
  const { t, lang } = useI18n();
  const t0 = toMs(place.t0_utc);
  const calibrated = !!meta?.calibrated;
  const peakVal = calibrated ? place.peak_smoke * meta!.alpha : place.peak_smoke;
  const already = place.arrival_utc != null && toMs(place.arrival_utc) <= t0 + 3600_000 && place.series[24] >= (meta?.arrival_threshold ?? 0);
  return (
    <div className={cn("grid grid-cols-2 gap-4", large && "sm:gap-8")}>
      <div>
        <p className="text-xs text-muted-foreground">{already ? t("place.already") : t("place.arrives")}</p>
        {place.arrival_utc ? (
          <>
            <p className={cn("mt-0.5 font-semibold tracking-tight", large ? "text-4xl" : "text-2xl")}>
              {already ? istTime(place.arrival_utc) : istDayTime(place.arrival_utc, lang)}
            </p>
            {place.arrival_window && !already && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {t("place.window", { a: istDayTime(place.arrival_window[0], lang), b: istDayTime(place.arrival_window[1], lang) })}
              </p>
            )}
          </>
        ) : (
          <p className="mt-1 text-sm">{t("place.noArrival")}</p>
        )}
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{t("place.peak")}</p>
        <p className={cn("mt-0.5 font-semibold tracking-tight", large ? "text-4xl" : "text-2xl")}>{istDayTime(place.peak_utc, lang)}</p>
        <div className="mt-1">
          {calibrated ? (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <NaqiChip category={naqiFromPm25(peakVal)} />
              <span className="font-mono text-xs text-muted-foreground">{Math.round(peakVal)} µg/m³</span>
            </div>
          ) : (
            <span className="font-mono text-xs text-muted-foreground">
              {t("place.smokeIndex")} {place.peak_smoke.toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function AqNowChip({ place }: { place: PlaceDetail }) {
  const { t } = useI18n();
  const aq = place.aq_now;
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <div className="min-w-0">
        <SectionLabel>{t("place.aq")}</SectionLabel>
        {aq ? (
          <p className="truncate text-xs text-muted-foreground">
            {aq.station} · {istTime(aq.obs_utc)} IST · {ageLabel(aq.obs_utc)}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">{t("place.aqNone")}</p>
        )}
      </div>
      {aq && <NaqiChip category={aq.category} value={aq.pm25} />}
    </div>
  );
}

export function PlaceCardSkeleton() {
  return (
    <div className="space-y-5 p-5" aria-busy="true">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-7 w-56" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
      <Skeleton className="h-48" />
      <Skeleton className="h-24" />
    </div>
  );
}

export function PlaceCard({
  placeId,
  onClose,
  showFullLink = true,
}: {
  placeId: string;
  onClose?: () => void;
  showFullLink?: boolean;
}) {
  const res = usePlace(placeId);
  const meta = useMeta();
  const hour = useHour();
  const { t, kind } = useI18n();

  if (res.status === "loading" || res.status === "idle") return <PlaceCardSkeleton />;
  if (res.status !== "ready")
    return (
      <div className="flex items-start justify-between gap-3 p-5">
        <p className="text-sm text-muted-foreground">{t("place.notFound")}</p>
        {onClose && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("place.close")}>
            <XIcon />
          </Button>
        )}
      </div>
    );
  const place = res.data;
  return (
    <article className="space-y-6 p-5" aria-labelledby="place-title">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-mono">{kind(place.kind)}</p>
          <h2 id="place-title" className="mt-1 text-xl leading-tight font-semibold tracking-tight">
            {place.name}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {place.district}, {place.state}
          </p>
        </div>
        <div className="-mt-1 -mr-2 flex shrink-0 items-center">
          <Button variant="ghost" size="icon-sm" onClick={() => sharePlace(place.id, place.name, t("place.copied"))} aria-label={t("place.share")}>
            <Share2Icon />
          </Button>
          {showFullLink && (
            <Button variant="ghost" size="icon-sm" asChild>
              <Link href={`/place/?id=${encodeURIComponent(place.id)}`} aria-label={t("place.open")}>
                <ExternalLinkIcon />
              </Link>
            </Button>
          )}
          {onClose && (
            <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("place.close")}>
              <XIcon />
            </Button>
          )}
        </div>
      </header>

      <ArrivalPeak place={place} meta={meta.data} />
      <ForecastChart place={place} meta={meta.data} cursorHour={hour} />
      <AttributionBars place={place} />
      <AqNowChip place={place} />
      <AskPanel placeId={place.id} placeName={place.name} />
    </article>
  );
}
