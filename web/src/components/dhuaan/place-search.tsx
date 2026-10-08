"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useSyncExternalStore } from "react";
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
  const { t, kind, lang } = useI18n();
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

  const groups = useMemo(() => {
    const places = idx.data?.places ?? [];
    const by = new Map<PlaceKind, PlaceIndexEntry[]>();
    for (const p of places) {
      if (kinds && !kinds.includes(p.kind)) continue;
      const arr = by.get(p.kind) ?? [];
      arr.push(p);
      by.set(p.kind, arr);
    }
    return KIND_ORDER.filter((k) => by.has(k)).map((k) => [k, by.get(k)!.sort((a, b) => a.name.localeCompare(b.name))] as const);
  }, [idx.data, kinds]);

  const choose = (p: PlaceIndexEntry) => {
    setSearchOpen(false);
    if (onSelect) onSelect(p);
    else router.push(`/?place=${encodeURIComponent(p.id)}`);
  };

  return (
    <CommandDialog open={isOpen} onOpenChange={setSearchOpen} title={t("search.placeholder")} description={t("search.placeholder")}>
      <Command>
      <CommandInput placeholder={t("search.placeholder")} />
      <CommandList className="max-h-[min(60vh,420px)]">
        <CommandEmpty>{idx.status === "loading" ? t("common.loading") : t("search.empty")}</CommandEmpty>
        {groups.map(([k, list]) => (
          <CommandGroup key={k} heading={kind(k)}>
            {list.map((p) => (
              <CommandItem key={p.id} value={`${p.name} ${p.district} ${p.state} ${p.id}`} onSelect={() => choose(p)}>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate">{p.name}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {p.district}, {p.state}
                  </span>
                </div>
                <span className="ml-3 shrink-0 font-mono text-xs text-muted-foreground">
                  {p.arrival_utc ? `${t("search.arrives")} ${istDayTime(p.arrival_utc, lang)}` : t("search.noSmoke")}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
      </Command>
    </CommandDialog>
  );
}
