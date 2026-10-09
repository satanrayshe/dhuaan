import type { Lang, UtcIso } from "./types";

export const HOUR_MS = 3600_000;
export const IST_OFFSET_MS = 5.5 * HOUR_MS;
/** model run covers t0-24h .. t0+72h, 97 hourly steps; index 0 = t0-24h */
export const H_MIN = -24;
export const H_MAX = 72;
export const N_HOURS = 97;

const LOCALE: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", pa: "pa-IN" };

const fmtCache = new Map<string, Intl.DateTimeFormat>();
function fmt(lang: Lang, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = lang + JSON.stringify(opts);
  let f = fmtCache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat(LOCALE[lang], { timeZone: "Asia/Kolkata", numberingSystem: "latn", ...opts });
    fmtCache.set(key, f);
  }
  return f;
}

export const toMs = (iso: UtcIso) => Date.parse(iso);

/** "21:00" in IST */
export function istTime(iso: UtcIso | number): string {
  const d = typeof iso === "number" ? new Date(iso) : new Date(iso);
  return fmt("en", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d);
}

// CLDR short names, for engines that ship no Punjabi date data (Chromium/Edge format pa-IN in English)
const PA_WEEKDAYS = ["ਐਤ", "ਸੋਮ", "ਮੰਗਲ", "ਬੁੱਧ", "ਵੀਰ", "ਸ਼ੁੱਕਰ", "ਸ਼ਨਿੱਚਰ"];
const PA_MONTHS = ["ਜਨ", "ਫ਼ਰ", "ਮਾਰਚ", "ਅਪ੍ਰੈ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾ", "ਅਗ", "ਸਤੰ", "ਅਕਤੂ", "ਨਵੰ", "ਦਸੰ"];
const SCRIPT: Partial<Record<Lang, RegExp>> = { hi: /[\u0900-\u097f]/, pa: /[\u0a00-\u0a7f]/ };

function istParts(d: Date) {
  const ist = new Date(d.getTime() + IST_OFFSET_MS);
  return { weekday: ist.getUTCDay(), day: ist.getUTCDate(), month: ist.getUTCMonth() };
}

/**
 * Some engines ship no CLDR names for pa/hi: they fall back to "M10"/"W3" or to English.
 * Punjabi gets the built-in table above; anything else falls back to English.
 */
function localised(lang: Lang, opts: Intl.DateTimeFormatOptions, d: Date): string {
  const out = fmt(lang, opts).format(d);
  if (lang === "en" || SCRIPT[lang]?.test(out)) return out;
  if (lang === "pa") {
    const p = istParts(d);
    if (opts.weekday) return PA_WEEKDAYS[p.weekday];
    if (opts.month) return `${p.day} ${PA_MONTHS[p.month]}`;
  }
  return /(^|\s)[MW]\d/.test(out) ? fmt("en", opts).format(d) : out;
}

/** "Sat 23:00" in IST, weekday localised */
export function istDayTime(iso: UtcIso | number, lang: Lang = "en"): string {
  const d = new Date(iso);
  return `${localised(lang, { weekday: "short" }, d)} ${istTime(d.getTime())}`;
}

/** "8 Oct" */
export function istDate(iso: UtcIso | number, lang: Lang = "en"): string {
  return localised(lang, { day: "numeric", month: "short" }, new Date(iso));
}

/** IST wall-clock hour (fractional) of a UTC instant */
export function istHourOf(ms: number): number {
  return ((((ms + IST_OFFSET_MS) / HOUR_MS) % 24) + 24) % 24;
}

/** offset hour (-24..72) -> UTC ms */
export function offsetToMs(t0: UtcIso, h: number): number {
  return toMs(t0) + h * HOUR_MS;
}

/** UTC iso -> offset hour relative to t0 (fractional) */
export function msToOffset(t0: UtcIso, ms: number): number {
  return (ms - toMs(t0)) / HOUR_MS;
}

/** "4 h" / "35 min" / "2 d" age */
export function ageLabel(iso: UtcIso | null | undefined, now = Date.now()): string {
  if (!iso) return "-";
  const mins = Math.max(0, Math.round((now - toMs(iso)) / 60000));
  if (mins < 60) return `${mins} min`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h} h`;
  return `${Math.round(h / 24)} d`;
}

/** true when IST hour is between sunset and sunrise (rough, Oct-Nov North India) */
export function isNightIst(ms: number): boolean {
  const h = istHourOf(ms);
  return h >= 18 || h < 6.5;
}

/**
 * Relative boundary-layer depth 0..1 for an instant: the fallback when grid.json has no
 * `blh_m` (older runs, fixtures). A typical diurnal cycle (shallow at night, deep in the
 * early afternoon), labelled as such in the UI.
 */
export function mixingDepth(ms: number): number {
  const h = istHourOf(ms);
  if (h <= 7 || h >= 18) return 0.08;
  return 0.08 + 0.92 * Math.sin((Math.PI * (h - 7)) / 11);
}
