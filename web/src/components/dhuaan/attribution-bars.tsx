"use client";

import { isAbroad } from "@/lib/derive";
import { useI18n } from "@/lib/i18n";
import type { PlaceDetail } from "@/lib/types";
import { SectionLabel } from "./bits";

export function AttributionBars({ place }: { place: PlaceDetail }) {
  const { t } = useI18n();
  const rows = [...place.attribution].sort((a, b) =>
    a.district === "Other" ? 1 : b.district === "Other" ? -1 : b.share - a.share,
  );
  const max = Math.max(0.01, ...rows.map((r) => r.share));
  return (
    <section aria-labelledby={`attr-${place.id}`}>
      <SectionLabel id={`attr-${place.id}`}>{t("place.from")}</SectionLabel>
      <p className="mt-0.5 text-xs text-muted-foreground">{t("place.fromNote")}</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">{t("place.fromNone")}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {rows.map((r) => (
            <li key={r.district + r.state} className="grid grid-cols-[minmax(0,8.5rem)_1fr_2.75rem] items-center gap-3 text-sm">
              <span className="truncate">
                {r.district === "Other" ? t("place.other") : r.district}
                {r.state && r.district !== "Other" && <span className="text-muted-foreground"> · {abbrevState(r.state)}</span>}
              </span>
              <span className="relative h-2 rounded-[2px] bg-muted" aria-hidden>
                <span
                  className="absolute inset-y-0 left-0 rounded-[2px]"
                  style={{
                    width: `${(r.share / max) * 100}%`,
                    background: r.district === "Other" ? "var(--muted-foreground)" : "var(--smoke)",
                    opacity: r.district === "Other" ? 0.45 : 1,
                  }}
                />
              </span>
              <span className="text-right font-mono text-xs">{Math.round(r.share * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
      {rows.some((r) => isAbroad(r.state)) && <p className="mt-2 text-xs text-muted-foreground">{t("place.abroadNote")}</p>}
    </section>
  );
}

function abbrevState(s: string) {
  const m: Record<string, string> = {
    Punjab: "PB", Haryana: "HR", Delhi: "DL", "Uttar Pradesh": "UP", Rajasthan: "RJ", Chandigarh: "CH",
    "Himachal Pradesh": "HP", Uttarakhand: "UK", "Jammu and Kashmir": "JK", "Punjab (Pakistan)": "PK",
  };
  return m[s] ?? s;
}
