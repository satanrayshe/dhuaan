import type { NaqiCategory } from "./types";

/**
 * Colour tokens for data marks. Every ramp here was run through the dataviz
 * validator (scripts/validate_palette.js) against the surface it sits on:
 *
 * smoke light  (ordinal, surface #fafaf8): monotone L, adjacent dL >= .06, light end 2.13:1, hue spread 14deg  PASS
 * smoke dark   (ordinal, surface #0f1113): monotone L, adjacent dL >= .06, light end 2.62:1, hue spread 15deg  PASS
 * NAQI light   (6 slots, adjacent, surface #ffffff): band/chroma PASS, CVD 10.3 PASS, normal 19.5 PASS,
 *              contrast WARN for satisfactory/poor -> relief: every NAQI swatch ships with a text label.
 * NAQI dark    (6 slots, adjacent, surface #0f1113): band/chroma PASS, CVD 8.0 (target), normal 15.2 PASS,
 *              contrast WARN for severe 2.9:1 -> relief: text label always shown.
 * Backtest     (3 slots, documented default palette slots 1-3, validated all-pairs in both modes).
 */

export type ThemeName = "light" | "dark";

/** smoke ramp, low -> high density. Light surfaces darken with density; dark surfaces brighten. */
export const SMOKE_RAMP: Record<ThemeName, string[]> = {
  light: ["#d6a650", "#bf8429", "#a1681d", "#835218", "#643e12", "#452a0b"],
  dark: ["#74501a", "#93681e", "#b28123", "#cf9a2c", "#e5b447", "#f3cb6c", "#fde3a2"],
};

export const NAQI_COLORS: Record<ThemeName, Record<NaqiCategory, string>> = {
  light: {
    good: "#207d44",
    satisfactory: "#9bc258",
    moderate: "#8d7819",
    poor: "#f49037",
    very_poor: "#e12526",
    severe: "#7f363e",
  },
  dark: {
    good: "#2d7346",
    satisfactory: "#77a031",
    moderate: "#7c650a",
    poor: "#ca7d22",
    very_poor: "#d92600",
    severe: "#9b3b67",
  },
};

/** NAQI PM2.5 breakpoints (upper bounds, ug/m3) per CONTRACTS. */
export const NAQI_BREAKS: [NaqiCategory, number][] = [
  ["good", 30],
  ["satisfactory", 60],
  ["moderate", 90],
  ["poor", 120],
  ["very_poor", 250],
  ["severe", Infinity],
];

export function naqiFromPm25(pm: number): NaqiCategory {
  for (const [cat, hi] of NAQI_BREAKS) if (pm <= hi) return cat;
  return "severe";
}

/** fires: one hot hue; afternoon/geostationary detections differ by SHAPE (ring), not colour */
export const FIRE_COLOR: Record<ThemeName, [number, number, number]> = {
  light: [214, 64, 12],
  dark: [255, 106, 51],
};

export const BACKTEST_COLORS: Record<ThemeName, { obs: string; A: string; B: string }> = {
  light: { obs: "#2a78d6", A: "#eb6834", B: "#1baf7a" },
  dark: { obs: "#3987e5", A: "#d95926", B: "#199e70" },
};

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

/**
 * 256-entry RGBA lookup for the smoke field bitmap. Value 0 is transparent; opacity
 * and ramp position both rise with density (single spectral treatment).
 */
export function smokeLut(theme: ThemeName): Uint8ClampedArray {
  const ramp = SMOKE_RAMP[theme].map(hexToRgb);
  const lut = new Uint8ClampedArray(256 * 4);
  for (let v = 0; v < 256; v++) {
    const x = v / 255;
    if (v < 6) continue; // leave near-zero transparent
    const pos = Math.min(ramp.length - 1.0001, Math.sqrt(x) * (ramp.length - 1));
    const i = Math.floor(pos);
    const f = pos - i;
    const a = ramp[i], b = ramp[i + 1];
    lut[v * 4] = a[0] + (b[0] - a[0]) * f;
    lut[v * 4 + 1] = a[1] + (b[1] - a[1]) * f;
    lut[v * 4 + 2] = a[2] + (b[2] - a[2]) * f;
    const maxA = theme === "dark" ? 0.78 : 0.7;
    lut[v * 4 + 3] = 255 * Math.min(maxA, 0.1 + Math.pow(x, 0.7) * maxA);
  }
  return lut;
}
