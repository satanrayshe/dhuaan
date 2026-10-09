"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { SearchIcon } from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { useReceptors } from "@/lib/data";
import { useI18n } from "@/lib/i18n";
import { istDayTime } from "@/lib/time";
import type { PlaceIndexEntry, PlaceKind } from "@/lib/types";
import { cn } from "@/lib/utils";

// open-state store so any component (coach marks, empty states) can open search
let open = false;
const subs = new Set<() => void>();
export function setSearchOpen(v: boolean) {
  open = v;
  subs.forEach((s) => s());
}
function useSearchOpen() {
  return useSyncExternalStore(
    (cb) => {
      subs.add(cb);
      return () => subs.delete(cb);
    },
    () => open,
    () => false,
  );
}

const KIND_ORDER: PlaceKind[] = ["ward", "school", "city", "town", "village"];
// the demo places (backend/data/demo_places.json) win ties, so "Bhawanigarh" opens the demo school
const DEMO = new Set(["osm-w1090680897", "dlw-21", "gn-1260107"]);
const PER_KIND = 8;
const MAX_RESULTS = 40;

const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

/**
 * Rank a place for a query: whole-name match > name starts with it > a word in the name starts
 * with it > substring of the name > district/state word match. 0 = no match. (cmdk's built-in
 * fuzzy scorer matched letters scattered across long school names, e.g. "Rohini" -> "Adesh Group…")
 */
function score(p: PlaceIndexEntry, q: string): number {
  const name = norm(p.name);
  if (name === q) return 100;
  if (name.startsWith(q)) return 80;
  const words = name.split(/[^a-z0-9\u0900-\u0a7f]+/);
  if (words.some((w) => w.startsWith(q))) return 60;
  if (name.includes(q)) return 40;
  const where = norm(`${p.district} ${p.state}`).split(/[^a-z0-9]+/);
  if (where.some((w) => w.startsWith(q))) return 20;
  return 0;
}

export function SearchButton({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      data-coach="search"
      onClick={() => setSearchOpen(true)}
      className={cn(
        "flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        className,
      )}
      aria-label={t("search.placeholder")}
    >
      <SearchIcon className="size-4 shrink-0" aria-hidden />
      <span className="hidden truncate md:inline">{t("search.placeholder")}</span>
      <span className="truncate md:hidden">{t("search.short")}</span>
      <Kbd className="ml-auto hidden md:inline-flex">⌘K</Kbd>
    </button>
  );
}

export function PlaceSearchDialog({
  onSelect,
  kinds,
}: {
  onSelect?: (p: PlaceIndexEntry) => void;
  kinds?: PlaceKind[];
}) {
  const isOpen = useSearchOpen();
  const router = useRouter();
  const { t, kind } = useI18n();
  const idx = useReceptors();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSearchOpen(!open);
      }
      if (e.key === "/" && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const [query, setQuery] = useState("");
  // closing clears the query (adjusting state during render, not in an effect)
  const [wasOpen, setWasOpen] = useState(isOpen);
  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (!isOpen) setQuery("");
  }

  const pool = useMemo(() => (idx.data?.places ?? []).filter((p) => !kinds || kinds.includes(p.kind)), [idx.data, kinds]);

  // typed: one ranked list (best match first, so Enter picks it). Empty: a short list per kind.
  const results = useMemo(() => {
    const q = norm(query.trim());
    if (!q) return null;
    return pool
      .map((p) => ({ p, s: score(p, q) }))
      .filter((r) => r.s > 0)
      .sort(
        (a, b) =>
          b.s - a.s ||
          Number(DEMO.has(b.p.id)) - Number(DEMO.has(a.p.id)) ||
          KIND_ORDER.indexOf(a.p.kind) - KIND_ORDER.indexOf(b.p.kind) ||
          a.p.name.length - b.p.name.length,
      )
      .slice(0, MAX_RESULTS)
      .map((r) => r.p);
  }, [pool, query]);

  const groups = useMemo(() => {
    const by = new Map<PlaceKind, PlaceIndexEntry[]>();
    for (const p of pool) {
      const arr = by.get(p.kind) ?? [];
      arr.push(p);
      by.set(p.kind, arr);
    }
    // browsing: demo places first, then where smoke arrives soonest
    const rank = (p: PlaceIndexEntry) => (DEMO.has(p.id) ? -2 : p.arrival_utc ? -1 : 0);
    return KIND_ORDER.filter((k) => by.has(k)).map(
      (k) => [k, by.get(k)!.sort((a, b) => rank(a) - rank(b) || (b.peak_smoke ?? 0) - (a.peak_smoke ?? 0)).slice(0, PER_KIND)] as const,
    );
  }, [pool]);

  const choose = (p: PlaceIndexEntry) => {
    setSearchOpen(false);
    if (onSelect) onSelect(p);
    else router.push(`/?place=${encodeURIComponent(p.id)}`);
  };

  return (
    <CommandDialog open={isOpen} onOpenChange={setSearchOpen} title={t("search.placeholder")} description={t("search.placeholder")}>
      <Command shouldFilter={false}>
      <CommandInput placeholder={t("search.placeholder")} value={query} onValueChange={setQuery} />
      {/* key: each query remounts the list, so it starts scrolled to the top with the best match selected */}
      <CommandList key={query.trim() || "browse"} className="max-h-[min(60vh,420px)]">
        <CommandEmpty>{idx.status === "loading" ? t("common.loading") : t("search.empty")}</CommandEmpty>
        {results
          ? results.length > 0 && (
              <CommandGroup>
                {results.map((p) => (
                  <Row key={p.id} p={p} onPick={choose} sub={`${kind(p.kind)} · ${p.district}, ${p.state}`} />
                ))}
              </CommandGroup>
            )
          : groups.map(([k, list]) => (
              <CommandGroup key={k} heading={kind(k)}>
                {list.map((p) => (
                  <Row key={p.id} p={p} onPick={choose} sub={`${p.district}, ${p.state}`} />
                ))}
              </CommandGroup>
            ))}
      </CommandList>
      </Command>
    </CommandDialog>
  );
}

function Row({ p, sub, onPick }: { p: PlaceIndexEntry; sub: string; onPick: (p: PlaceIndexEntry) => void }) {
  const { t, lang } = useI18n();
  return (
    <CommandItem value={p.id} onSelect={() => onPick(p)}>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate">{p.name}</span>
        <span className="truncate text-xs text-muted-foreground">{sub}</span>
      </div>
      <span className="ml-3 shrink-0 font-mono text-xs text-muted-foreground">
        {p.arrival_utc ? `${t("search.arrives")} ${istDayTime(p.arrival_utc, lang)}` : t("search.noSmoke")}
      </span>
    </CommandItem>
  );
}
