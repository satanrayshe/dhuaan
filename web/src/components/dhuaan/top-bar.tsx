"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";
import { MenuIcon, MoonIcon, SunIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isStale, useMeta } from "@/lib/data";
import { LANGS, useI18n, type DictKey } from "@/lib/i18n";
import { ageLabel, istTime } from "@/lib/time";
import type { Lang, SourceStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PlaceSearchDialog, SearchButton } from "./place-search";

const NAV: { href: string; key: DictKey }[] = [
  { href: "/", key: "nav.map" },
  { href: "/schools/", key: "nav.schools" },
  { href: "/district/", key: "nav.district" },
  { href: "/backtest/", key: "nav.backtest" },
  { href: "/how-it-works/", key: "nav.how" },
];

export function LogoMark({ className }: { className?: string }) {
  // three drifting smoke strokes; the leading one carries the smoke hue
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <path d="M4 21c4-3 8-3 12 0s8 3 12 0" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" opacity=".35" />
      <path d="M4 15c4-3 8-3 12 0s8 3 12 0" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" opacity=".7" />
      <path d="M4 9c4-3 8-3 12 0s8 3 12 0" fill="none" stroke="var(--smoke)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <Link href="/" className="group flex shrink-0 items-center gap-2 rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none" aria-label="Dhuaan home">
      <LogoMark />
      <span className="flex items-baseline gap-1.5">
        <span className="text-[1.05rem] font-semibold tracking-tight">Dhuaan</span>
        <span className="hidden text-sm text-muted-foreground sm:inline" lang="pa">
          ਧੂੰਆਂ
        </span>
        <span className="hidden text-sm text-muted-foreground sm:inline" lang="hi">
          धुआँ
        </span>
      </span>
    </Link>
  );
}

function shortSource(name: string): string {
  if (/viirs/i.test(name)) return "VIIRS";
  if (/modis/i.test(name)) return "MODIS";
  if (/msg|iodc|lsa/i.test(name)) return "MSG-IODC";
  if (/gk2a/i.test(name)) return "GK2A";
  if (/gfs/i.test(name)) return "GFS";
  if (/open-?meteo/i.test(name)) return "Open-Meteo";
  if (/openaq/i.test(name)) return "OpenAQ";
  return name.split(/\s+/).slice(-1)[0];
}

function SourceChip({ s }: { s: SourceStatus }) {
  const { t } = useI18n();
  const ok = s.ok;
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[0.7rem] whitespace-nowrap text-muted-foreground">
      <span
        className={cn("size-1.5 rounded-full", ok ? "bg-[#207d44] dark:bg-[#37b24d]" : "bg-destructive")}
        aria-hidden
      />
      <span className="text-foreground">{shortSource(s.name)}</span>
      {ok && s.latest_obs_utc ? <span>{istTime(s.latest_obs_utc)}</span> : <span>{t("fresh.down")}</span>}
    </span>
  );
}

function Freshness() {
  const meta = useMeta();
  const { t } = useI18n();
  if (meta.status !== "ready") return null;
  const sources = meta.data.sources ?? [];
  const stale = isStale(meta.data);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="hidden items-center gap-3 rounded-md px-2 py-1 transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none lg:flex"
          aria-label={t("fresh.title")}
        >
          {sources.slice(0, 3).map((s, i) => (
            <span key={s.name} className={i === 2 ? "hidden 2xl:inline-flex" : "inline-flex"}>
              <SourceChip s={s} />
            </span>
          ))}
          {stale && <span className="font-mono text-[0.7rem] text-destructive">{t("fresh.old")}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-medium">{t("fresh.title")}</p>
          <p className="font-mono text-xs text-muted-foreground">
            run {meta.data.run_id} · t0 {istTime(meta.data.t0_utc)} IST · {ageLabel(meta.data.generated_utc)}
          </p>
        </div>
        <ul className="divide-y divide-border">
          {sources.map((s) => (
            <li key={s.name} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm">{s.name}</p>
                {s.note && <p className="truncate text-xs text-muted-foreground">{s.note}</p>}
              </div>
              <div className="shrink-0 text-right font-mono text-xs">
                <p className={s.ok ? "text-foreground" : "text-destructive"}>
                  {s.ok && s.latest_obs_utc ? `${istTime(s.latest_obs_utc)} IST` : t("fresh.down")}
                </p>
                <p className="text-muted-foreground">
                  {s.latest_obs_utc ? `${ageLabel(s.latest_obs_utc)} · ` : ""}n={s.count.toLocaleString("en-IN")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export function SampleBadge({ className }: { className?: string }) {
  const meta = useMeta();
  const { t } = useI18n();
  if (meta.status !== "ready" || !meta.data.synthetic) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex h-6 shrink-0 items-center rounded-sm border border-dashed border-smoke px-2 font-mono text-[0.68rem] tracking-wide text-smoke uppercase",
            className,
          )}
        >
          {t("sample.badge")}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{t("sample.tooltip")}</TooltipContent>
    </Tooltip>
  );
}

export function LangToggle({ className }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      spacing={0}
      value={lang}
      onValueChange={(v) => v && setLang(v as Lang)}
      aria-label={t("lang.label")}
      className={className}
    >
      {LANGS.map((l) => (
        <ToggleGroupItem key={l.id} value={l.id} aria-label={l.name} className="min-w-9 px-2 text-xs">
          {l.short}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const { t } = useI18n();
  const next = resolvedTheme === "dark" ? "light" : "dark";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={() => setTheme(next)} aria-label={t("theme.toggle")}>
          <SunIcon className="hidden size-4 dark:block" aria-hidden />
          <MoonIcon className="size-4 dark:hidden" aria-hidden />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t("theme.toggle")}</TooltipContent>
    </Tooltip>
  );
}

function NavLinks({ vertical = false, onNavigate }: { vertical?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const norm = (p: string) => (p.endsWith("/") ? p : p + "/");
  return (
    <nav aria-label="Main" className={cn("flex", vertical ? "flex-col gap-1" : "items-center gap-0.5")}>
      {NAV.map((n) => {
        const active = n.href === "/" ? pathname === "/" || pathname === "/place/" || pathname === "/place" : norm(pathname).startsWith(n.href);
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
              vertical && "px-3 py-2 text-base",
            )}
          >
            {t(n.key)}
          </Link>
        );
      })}
    </nav>
  );
}

export function TopBar() {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <header className="no-print sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
      <div className="flex h-14 items-center gap-3 px-3 sm:px-4">
        <Wordmark />
        <div className="hidden xl:block">
          <NavLinks />
        </div>
        <SearchButton className="ml-auto w-auto max-w-80 min-w-0 flex-1 sm:flex-none md:w-64 xl:ml-2 2xl:w-72" />
        <div className="flex items-center gap-2 xl:ml-auto">
          <Freshness />
          <SampleBadge className="hidden sm:inline-flex" />
          <LangToggle className="hidden md:flex" />
          <ThemeToggle />
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="xl:hidden" aria-label={t("nav.menu")}>
                <MenuIcon className="size-5" aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetHeader>
                <SheetTitle>
                  <Wordmark />
                </SheetTitle>
              </SheetHeader>
              <div className="flex flex-col gap-6 px-4">
                <NavLinks vertical onNavigate={() => setMenuOpen(false)} />
                <LangToggle className="md:hidden" />
                <SampleBadge className="self-start sm:hidden" />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
      <PlaceSearchDialog />
    </header>
  );
}
