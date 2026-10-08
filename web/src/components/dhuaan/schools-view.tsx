"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CheckIcon, ChevronsUpDownIcon, CopyIcon, MinusIcon, PrinterIcon, SendIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NAQI_COLORS, naqiFromPm25 } from "@/lib/colors";
import { API_BASE, useAdvisoryArtifact, useMeta, usePlace, useReceptors, useResource } from "@/lib/data";
import { useI18n, type DictKey } from "@/lib/i18n";
import { HOUR_MS, IST_OFFSET_MS, istDate, toMs } from "@/lib/time";
import type { Advisory, AdvisoryHour, Lang, Meta, OutdoorAdvice, PlaceDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { GroundingBadge } from "./ask-panel";
import { NaqiChip, useThemeName } from "./bits";

const OUTDOOR: Record<OutdoorAdvice, { key: DictKey; Icon: typeof CheckIcon }> = {
  ok: { key: "schools.ok", Icon: CheckIcon },
  limit: { key: "schools.limit", Icon: MinusIcon },
  indoors: { key: "schools.indoors", Icon: XIcon },
};

/** demo school (backend/data/demo_places.json); the one with a published advisory */
const DEMO_SCHOOL_ID = "osm-w1090680897";

/** advisories carry hour_ist as 7 or "07:00" */
function hourLabel(h: number | string): string {
  if (typeof h === "number") return `${String(h).padStart(2, "0")}:00`;
  return /^\d{1,2}$/.test(h) ? `${h.padStart(2, "0")}:00` : h;
}

function outdoorFor(pm: number): OutdoorAdvice {
  return pm <= 60 ? "ok" : pm <= 120 ? "limit" : "indoors";
}

/** Browser fallback: same deterministic rules as the advisory engine, from the place forecast. */
function computePlan(place: PlaceDetail, meta: Meta): { date: string; plan: AdvisoryHour[] } | null {
  if (!meta.calibrated) return null;
  const t0 = toMs(place.t0_utc);
  const nowIst = Date.now() + IST_OFFSET_MS;
  const dayStart = Math.floor(nowIst / (24 * HOUR_MS)) * 24 * HOUR_MS;
  const base = nowIst < dayStart + 8 * HOUR_MS ? dayStart : dayStart + 24 * HOUR_MS;
  const plan: AdvisoryHour[] = [];
  for (let h = 7; h <= 14; h++) {
    const utc = base - IST_OFFSET_MS + h * HOUR_MS;
    const idx = Math.round((utc - t0) / HOUR_MS) + 24;
    if (idx < 0 || idx >= place.series.length) return null;
    const pm = Math.round(place.series[idx] * meta.alpha);
    plan.push({ hour_ist: h, est_pm25: pm, category: naqiFromPm25(pm), outdoor: outdoorFor(pm) });
  }
  return { date: new Date(base).toISOString().slice(0, 10), plan };
}

function useAdvisory(schoolId: string | null, lang: Lang) {
  const art = useAdvisoryArtifact(schoolId);
  const needApi = !!schoolId && (art.status === "missing" || art.status === "error");
  const api = useResource<Advisory>(needApi ? `${API_BASE}/api/advisory?school_id=${encodeURIComponent(schoolId!)}&lang=${lang}` : null);
  if (art.status === "ready") return art;
  if (needApi) return api.status === "idle" ? { status: "loading" as const } : api;
  return art;
}

function Timeline({ plan }: { plan: AdvisoryHour[] }) {
  const { t } = useI18n();
  const theme = useThemeName();
  return (
    <ol className={cn("grid grid-cols-4 gap-1.5", plan.length === 7 ? "sm:grid-cols-7" : "sm:grid-cols-8")} aria-label="07:00 to 14:00 IST">
      {plan.map((p) => {
        const o = OUTDOOR[p.outdoor];
        return (
          <li key={p.hour_ist} className="flex flex-col overflow-hidden rounded-md border border-border">
            <span className="h-1.5" style={{ background: NAQI_COLORS[theme][p.category] }} aria-hidden />
            <div className="flex flex-1 flex-col gap-1.5 p-2">
              <span className="font-mono text-xs text-muted-foreground">{hourLabel(p.hour_ist)}</span>
              <span
                className={cn(
                  "inline-flex size-6 items-center justify-center rounded-full border",
                  p.outdoor === "ok" && "border-foreground/20",
                  p.outdoor === "limit" && "border-foreground/40 bg-muted",
                  p.outdoor === "indoors" && "border-foreground bg-foreground text-background",
                )}
                aria-hidden
              >
                <o.Icon className="size-3.5" />
              </span>
              <span className="text-xs leading-tight font-medium">{t(o.key)}</span>
              <span className="font-mono text-[0.7rem] whitespace-nowrap text-muted-foreground">{p.est_pm25} µg/m³</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Notice({ advisory, place }: { advisory: Advisory; place: PlaceDetail }) {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<Lang>(lang);
  const [copied, setCopied] = useState(false);
  const text = advisory.notice[tab];
  return (
    <section aria-labelledby="notice-title" className="rounded-lg border border-border">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <h2 id="notice-title" className="text-base font-semibold">
          {t("schools.notice")}
        </h2>
        <GroundingBadge verified={advisory.grounding.verified} total={advisory.grounding.total} />
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as Lang)} className="p-4">
        <TabsList>
          <TabsTrigger value="en">English</TabsTrigger>
          <TabsTrigger value="hi">हिन्दी</TabsTrigger>
          <TabsTrigger value="pa">ਪੰਜਾਬੀ</TabsTrigger>
        </TabsList>
        {(["en", "hi", "pa"] as Lang[]).map((l) => (
          <TabsContent key={l} value={l} className="mt-3">
            <div className="print-area rounded-md bg-muted/60 p-4">
              <p className="hidden text-sm font-semibold print:block">
                {place.name} · {advisory.date_ist}
              </p>
              <p lang={l === "en" ? "en-IN" : l} className="text-[0.95rem] leading-relaxed whitespace-pre-line">
                {advisory.notice[l]}
              </p>
            </div>
          </TabsContent>
        ))}
        <div className="no-print mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigator.clipboard?.writeText(text).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              })
            }
          >
            {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />} {copied ? t("schools.copied") : t("schools.copy")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <PrinterIcon aria-hidden /> {t("schools.print")}
          </Button>
          <span className="ml-auto font-mono text-[0.7rem] text-muted-foreground">{advisory.model}</span>
        </div>
      </Tabs>
    </section>
  );
}

export function SchoolsView() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const idx = useReceptors();
  const meta = useMeta();
  const [open, setOpen] = useState(false);

  const schools = useMemo(() => (idx.data?.places ?? []).filter((p) => p.kind === "school"), [idx.data]);
  const fallbackId = useMemo(
    () => (schools.find((s) => s.id === DEMO_SCHOOL_ID) ?? schools.find((s) => /bhawanigarh/i.test(s.name)) ?? schools[0])?.id ?? null,
    [schools],
  );
  const schoolId = params.get("id") ?? fallbackId;
  const school = schools.find((s) => s.id === schoolId) ?? null;

  const place = usePlace(schoolId);
  const adv = useAdvisory(schoolId, lang);
  const computed = useMemo(
    () => (place.status === "ready" && meta.status === "ready" ? computePlan(place.data, meta.data) : null),
    [place, meta],
  );
  const advisory = adv.status === "ready" ? adv.data : null;
  const plan = advisory?.plan ?? computed?.plan ?? null;
  const date = advisory?.date_ist ?? computed?.date ?? null;
  const worst = plan?.reduce((a, b) => (b.est_pm25 > a.est_pm25 ? b : a));
  // no published advisory and no calibration to compute one from: say so, don't spin
  const loadingPlan = !plan && (adv.status === "loading" || place.status === "loading" || meta.status === "loading");
  const noPlan = !plan && !loadingPlan;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:py-12">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("schools.title")}</h1>
          <p className="mt-2 text-muted-foreground">{t("schools.subtitle")}</p>
        </div>
      </header>
      <p className="mt-4 text-xs text-muted-foreground">{t("schools.persona")}</p>

      <div className="mt-8">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" role="combobox" aria-expanded={open} className="h-11 w-full justify-between sm:w-[28rem]">
              <span className="truncate">{school?.name ?? t("schools.search")}</span>
              <ChevronsUpDownIcon className="opacity-50" aria-hidden />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[min(28rem,calc(100vw-2rem))] p-0" align="start">
            <Command>
              <CommandInput placeholder={t("schools.search")} />
              <CommandList>
                <CommandEmpty>{t("schools.none")}</CommandEmpty>
                <CommandGroup>
                  {schools.map((s) => (
                    <CommandItem
                      key={s.id}
                      value={`${s.name} ${s.district}`}
                      onSelect={() => {
                        setOpen(false);
                        router.replace(`/schools/?id=${encodeURIComponent(s.id)}`, { scroll: false });
                      }}
                    >
                      <CheckIcon className={cn(s.id === schoolId ? "opacity-100" : "opacity-0")} aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{s.name}</span>
                      <span className="text-xs text-muted-foreground">{s.district}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>

      {idx.status === "ready" && schools.length === 0 && <p className="mt-8 text-muted-foreground">{t("schools.none")}</p>}

      {schoolId && (
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="min-w-0 space-y-8">
            <section aria-labelledby="plan-title" className="rounded-lg border border-border p-4 sm:p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="plan-title" className="text-base font-semibold">
                  {date
                    ? t("schools.today", { date: istDate(Date.parse(date + "T06:30:00Z"), lang) })
                    : noPlan
                      ? t("schools.noPlan")
                      : t("common.loading")}
                </h2>
                {worst && <NaqiChip category={worst.category} value={worst.est_pm25} />}
              </div>
              {worst && (
                <p className="mt-1 text-2xl font-semibold tracking-tight">{t(OUTDOOR[worst.outdoor].key)}</p>
              )}
              <div className="mt-4">
                {plan ? (
                  <Timeline plan={plan} />
                ) : loadingPlan ? (
                  <Skeleton className="h-28" />
                ) : (
                  <div className="space-y-3 text-sm text-muted-foreground">
                    <p>{meta.data && !meta.data.calibrated ? t("schools.noPlanUncal") : t("schools.computed")}</p>
                    {schoolId !== DEMO_SCHOOL_ID && schools.some((s) => s.id === DEMO_SCHOOL_ID) && (
                      <Button variant="outline" size="sm" onClick={() => router.replace(`/schools/?id=${DEMO_SCHOOL_ID}`, { scroll: false })}>
                        {t("schools.seeDemo")}
                      </Button>
                    )}
                  </div>
                )}
              </div>
              {!advisory && computed && <p className="mt-3 text-xs text-muted-foreground">{t("schools.computed")}</p>}
              <p className="mt-4 text-xs leading-relaxed text-muted-foreground">{t("schools.basis")}</p>
            </section>

            {advisory && place.status === "ready" && <Notice advisory={advisory} place={place.data} />}
          </div>

          <aside className="space-y-4">
            <section aria-labelledby="tg-title" className="rounded-lg border border-border p-4">
              <div className="flex items-center gap-2">
                <SendIcon className="size-4 text-muted-foreground" aria-hidden />
                <h2 id="tg-title" className="text-sm font-semibold">
                  {t("schools.tg.title")}
                </h2>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{t("schools.tg.body")}</p>
              <ol className="mt-4 space-y-2 text-sm">
                {t("schools.tg.steps")
                  .replace(/[.।]\s*$/, "")
                  .split(/,\s*/)
                  .map((step, i) => (
                    <li key={i} className="grid grid-cols-[1.25rem_1fr] gap-2">
                      <span className="font-mono text-xs leading-5 text-muted-foreground">{i + 1}</span>
                      <span>{step.charAt(0).toUpperCase() + step.slice(1)}</span>
                    </li>
                  ))}
              </ol>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
