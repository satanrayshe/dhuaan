/**
 * Calibration regions. Mirror of backend/dhuaan/geo/regions.py: keep NCR_DISTRICTS identical.
 * "delhi_ncr" = NCT of Delhi + adjacent urban NCR districts, "punjab_haryana" = rest of Punjab, Haryana,
 * Chandigarh, "_default" = elsewhere (pooled, pre-registered alpha).
 */
import type { Meta } from "./types";

export type CalRegion = "delhi_ncr" | "punjab_haryana" | "_default";

export const NCR_DISTRICTS = new Set([
  "Gurgaon", "Gurugram", "Faridabad", "Sonipat", "Jhajjar", "Palwal", // Haryana
  "Ghaziabad", "Gautam Buddha Nagar", "Baghpat", // Uttar Pradesh
]);
const DELHI_STATES = new Set(["Delhi", "NCT of Delhi"]);
const PUNJAB_HARYANA_STATES = new Set(["Punjab", "Haryana", "Chandigarh"]);

export const EST_LABEL = "est. smoke PM2.5 (provisional calibration)";

export function regionOf(district?: string | null, state?: string | null): CalRegion {
  if ((state && DELHI_STATES.has(state)) || (district && NCR_DISTRICTS.has(district))) return "delhi_ncr";
  if (state && PUNJAB_HARYANA_STATES.has(state)) return "punjab_haryana";
  return "_default";
}

/** Region-appropriate alpha (meta.alpha_by_region), else the pooled meta.alpha, else 1. */
export function alphaFor(meta: Meta | undefined, district?: string | null, state?: string | null): number {
  if (!meta) return 1;
  const by = meta.alpha_by_region;
  const v = by?.[regionOf(district, state)] ?? by?._default;
  return typeof v === "number" && v > 0 ? v : meta.alpha || 1;
}
