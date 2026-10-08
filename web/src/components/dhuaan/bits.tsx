"use client";

import { useTheme } from "next-themes";
import { NAQI_COLORS, type ThemeName } from "@/lib/colors";
import { useI18n } from "@/lib/i18n";
import type { NaqiCategory } from "@/lib/types";
import { cn } from "@/lib/utils";

export function useThemeName(): ThemeName {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? "dark" : "light";
}

/** NAQI category: swatch + text label, never colour alone */
export function NaqiChip({
  category,
  value,
  unit = "µg/m³",
  className,
  size = "md",
}: {
  category: NaqiCategory;
  value?: number;
  unit?: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const theme = useThemeName();
  const { naqi } = useI18n();
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border border-border bg-background font-medium whitespace-nowrap",
        size === "sm" ? "h-5 px-1.5 text-[0.7rem]" : "h-6 px-2 text-xs",
        className,
      )}
    >
      <span className="size-2 rounded-[2px]" style={{ background: NAQI_COLORS[theme][category] }} aria-hidden />
      {naqi(category)}
      {value != null && (
        <span className="font-mono font-normal text-muted-foreground">
          {Math.round(value)} {unit}
        </span>
      )}
    </span>
  );
}

export function SectionLabel({ children, className, id }: { children: React.ReactNode; className?: string; id?: string }) {
  return (
    <h3 id={id} className={cn("label-mono", className)}>
      {children}
    </h3>
  );
}

export function Stat({
  label,
  value,
  sub,
  className,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tracking-tight">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}
