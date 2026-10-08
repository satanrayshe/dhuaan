"use client";

import { useState } from "react";
import { LayersIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { SMOKE_RAMP } from "@/lib/colors";
import { useI18n, type DictKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useThemeName } from "./bits";
import type { MapLayersState } from "./smoke-map";

function Row({
  id,
  label,
  note,
  checked,
  onChange,
  legend,
  disabled,
}: {
  id: string;
  label: string;
  note?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  legend?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className="py-2">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className={cn("flex min-w-0 items-center gap-2 text-sm", disabled ? "text-muted-foreground" : "cursor-pointer")}>
          {legend}
          <span className="truncate">{label}</span>
        </label>
        <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} aria-describedby={note ? `${id}-note` : undefined} />
      </div>
      {note && (
        <p id={`${id}-note`} className="mt-0.5 pl-6 text-[0.7rem] leading-snug text-muted-foreground">
          {note}
        </p>
      )}
    </div>
  );
}

export function SmokeRampLegend({ className }: { className?: string }) {
  const theme = useThemeName();
  const { t } = useI18n();
  const ramp = SMOKE_RAMP[theme];
  return (
    <div className={className}>
      <p className="text-[0.7rem] text-muted-foreground">{t("legend.smoke")}</p>
      <div className="mt-1 flex h-2 overflow-hidden rounded-[2px]" aria-hidden>
        {ramp.map((c) => (
          <span key={c} className="flex-1" style={{ background: c }} />
        ))}
      </div>
      <div className="mt-0.5 flex justify-between font-mono text-[0.66rem] text-muted-foreground">
        <span>{t("legend.low")}</span>
        <span>{t("legend.high")}</span>
      </div>
    </div>
  );
}

export function LayerPanel({
  layers,
  setLayers,
  hasEvening,
  eveningNote,
  compare,
  setCompare,
  className,
  defaultOpen = true,
}: {
  layers: MapLayersState;
  setLayers: (l: MapLayersState) => void;
  hasEvening: boolean;
  /** shown instead of the layer when this run has no evening detections */
  eveningNote?: string;
  compare: boolean;
  setCompare: (v: boolean) => void;
  className?: string;
  defaultOpen?: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const set = (k: keyof MapLayersState) => (v: boolean) => setLayers({ ...layers, [k]: v });
  const fireDot = <span className="size-2.5 shrink-0 rounded-full bg-fire ring-1 ring-background" aria-hidden />;
  const ring = <span className="size-3 shrink-0 rounded-full border-[1.5px] border-fire bg-fire/15" aria-hidden />;
  const swatch = (i: number) => <SmokeSwatch i={i} />;

  if (!open)
    return (
      <Button variant="outline" size="sm" className={cn("bg-panel shadow-sm backdrop-blur", className)} onClick={() => setOpen(true)}>
        <LayersIcon aria-hidden /> {t("layers.title")}
      </Button>
    );

  const rows: { k: keyof MapLayersState; key: DictKey; legend: React.ReactNode; note?: string; show: boolean; disabled?: boolean }[] = [
    { k: "fires", key: "layers.fires", legend: fireDot, show: true },
    {
      k: "missed",
      key: "layers.missed",
      legend: ring,
      note: hasEvening ? t("layers.missedNote") : eveningNote,
      show: hasEvening || !!eveningNote,
      disabled: !hasEvening,
    },
    { k: "trails", key: "layers.trails", legend: swatch(4), show: true },
    { k: "field", key: "layers.field", legend: swatch(2), show: true },
    { k: "places", key: "layers.places", legend: <span className="size-2.5 shrink-0 rounded-full border-[1.5px] border-foreground bg-background" aria-hidden />, show: true },
  ];

  return (
    <section
      aria-label={t("layers.title")}
      className={cn(
        "w-64 rounded-lg border border-panel-border bg-panel px-3 py-2 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.18)] backdrop-blur-md",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <h2 className="label-mono">{t("layers.title")}</h2>
        <Button variant="ghost" size="icon-xs" onClick={() => setOpen(false)} aria-label={`${t("place.close")} ${t("layers.title")}`}>
          <XIcon />
        </Button>
      </div>
      <div className="divide-y divide-border">
        {rows
          .filter((r) => r.show)
          .map((r) => (
            <Row
              key={r.k}
              id={`layer-${r.k}`}
              label={t(r.key)}
              note={r.note}
              checked={r.disabled ? false : layers[r.k]}
              disabled={r.disabled}
              onChange={set(r.k)}
              legend={r.legend}
            />
          ))}
        {hasEvening && (
          <Row id="layer-compare" label={t("layers.compare")} checked={compare} onChange={setCompare} legend={<span className="h-3 w-2.5 shrink-0 border-r-2 border-foreground" aria-hidden />} />
        )}
      </div>
      <div className="mt-1 space-y-2 border-t border-border pt-2 pb-1">
        <SmokeRampLegend />
        <div className="flex items-center gap-2 text-[0.7rem] text-muted-foreground">
          <span className="flex items-end gap-1" aria-hidden>
            <span className="size-1.5 rounded-full bg-fire" />
            <span className="size-2.5 rounded-full bg-fire" />
            <span className="size-3.5 rounded-full bg-fire" />
          </span>
          {t("legend.fire")}
          {hasEvening && (
            <>
              <span className="ml-1 size-3 rounded-full border-[1.5px] border-fire" aria-hidden />
              {t("legend.ring")}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function SmokeSwatch({ i }: { i: number }) {
  const theme = useThemeName();
  return <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ background: SMOKE_RAMP[theme][i] }} aria-hidden />;
}
