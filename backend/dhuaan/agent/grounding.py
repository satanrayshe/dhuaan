"""Grounding check: every number in an answer must come from that turn's tool results.

What is extracted from the answer (after mapping Devanagari ०-९ and Gurmukhi ੦-੯ digits to ASCII):
  * clock times: "21:00", "9 pm", "9:30 p.m.", "8.30 am", "रात 9 बजे", "ਸਵੇਰੇ 8:30 ਵਜੇ"
  * numbers: integers, decimals, Indian/Western digit grouping ("1,23,456", "123,456"), percentages
    ("34%", "34 प्रतिशत"), and lakh/crore/million multipliers.
Not checked (removed before extraction), by rule:
  * pollutant and unit names: PM2.5, PM10, ug/m3 / µg/m³
  * identifiers that start with a letter (c0001, GK2A, NOAA-20, sch_demo_1)
  * list/ordinal markers: "1." / "2)" at the start of a line, and 1st/2nd/3rd/4th...
  * any number that also appears in the user's question (the user supplied it)
How a number is verified against the tool results (all numbers anywhere in the JSON, numbers inside strings,
list lengths, the tool arguments, date parts and clock times, with UTC timestamps also converted to IST):
  * rounding: the answer value equals a tool value rounded to the answer's decimals (108 <- 107.6, 30.91 <- 30.9123)
  * round numbers (not percentages): an integer >= 20 ending in 5 or 0 may be the tool value rounded to the nearest 5
    (or to the nearest 10 when the value is >= 50): "about 150" <- 147, "75" <- 73.6
  * shares: 34% <-> 0.34 and 34% <-> share_pct 34
  * clock times: same IST/UTC time within 30 minutes; "9 बजे" may be 09:00 or 21:00
Each distinct number string is counted once.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any, Iterable

from dhuaan.agent.timeutil import IST, parse_utc

_DIGITS = str.maketrans("०१२३४५६७८९੦੧੨੩੪੫੬੭੮੯", "01234567890123456789")
_PCT = r"(?:%|\s?(?:percent|per cent|प्रतिशत|फ़ीसदी|फीसदी|ਪ੍ਰਤੀਸ਼ਤ|ਫ਼ੀਸਦੀ|ਫੀਸਦੀ))"
_MULT = {"lakh": 1e5, "lakhs": 1e5, "लाख": 1e5, "ਲੱਖ": 1e5, "crore": 1e7, "crores": 1e7, "करोड़": 1e7,
         "करोड": 1e7, "ਕਰੋੜ": 1e7, "million": 1e6, "thousand": 1e3, "हज़ार": 1e3, "हजार": 1e3, "ਹਜ਼ਾਰ": 1e3}
_MULT_RE = "|".join(sorted((re.escape(k) for k in _MULT), key=len, reverse=True))

_EXCLUDE = [
    re.compile(r"(?i)\bPM\s*(?:2\.5|10)\b|PM₂\.₅|PM₁₀"),
    re.compile(r"(?i)[µμu]g\s*/\s*m\s*[3³]"),
    re.compile(r"(?i)\bm[3³]\b"),
    re.compile(r"(?<![\w])[A-Za-z_][A-Za-z_\-]*\d[\w\-]*"),  # identifiers like c0001, GK2A, NOAA-20
    re.compile(r"(?m)^\s*(?:[-*]\s*)?\d{1,2}[.)](?=\s)"),  # list markers
    re.compile(r"(?i)\b\d+(?:st|nd|rd|th)\b"),  # ordinals
]
_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# times: "21:00", "9:30 pm", "9 pm", "8.30 a.m.", "9 बजे", "8:30 ਵਜੇ"
_TIME_AMPM = re.compile(r"(?i)(?<![\d.:])(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?\s?m\b\.?")
_TIME_BAJE = re.compile(r"(?<![\d.:])(\d{1,2})(?::(\d{2}))?\s*(?:बजे|ਵਜੇ)")
_TIME_HHMM = re.compile(r"(?<![\d.:])(\d{1,2}):(\d{2})(?![\d:])")
_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{2,3})+(?=[^\d]|$)|\d+)(?:\.(\d+))?(" + _PCT + r")?(?:\s*(" + _MULT_RE + r"))?")


def normalise(text: str) -> str:
    return (text or "").translate(_DIGITS).replace(" ", " ").replace("−", "-")


def _blank(text: str, span: tuple[int, int]) -> str:
    return text[: span[0]] + " " * (span[1] - span[0]) + text[span[1]:]


def extract(text: str) -> tuple[list[dict], list[dict]]:
    """Return (times, numbers) found in text. times: {raw, h, m, ambiguous}; numbers: {raw, value, decimals, pct}."""
    t = normalise(text)
    for rx in _EXCLUDE:
        t = rx.sub(lambda m: " " * len(m.group(0)), t)
    t = _ISO_TS.sub(lambda m: m.group(0).replace("T", " ").replace("Z", " "), t)
    times: list[dict] = []
    for rx, kind in ((_TIME_AMPM, "ampm"), (_TIME_BAJE, "baje"), (_TIME_HHMM, "hhmm")):
        for m in list(rx.finditer(t)):
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if mi > 59 or h > 24:
                continue
            amb = False
            if kind == "ampm":
                if h > 12:
                    continue
                h = (h % 12) + (12 if m.group(3).lower() == "p" else 0)
            elif kind == "baje":
                amb = h <= 12
            times.append({"raw": m.group(0).strip(), "h": h % 24, "m": mi, "ambiguous": amb})
            t = _blank(t, m.span())
    nums: list[dict] = []
    for m in _NUM.finditer(t):
        ip, dp, pct, mult = m.group(1), m.group(2), m.group(3), m.group(4)
        v = float(ip.replace(",", "") + ("." + dp if dp else ""))
        k = _MULT[mult] if mult else 1.0
        d = len(dp or "")
        nums.append({"raw": m.group(0).strip(), "value": v * k, "decimals": d, "tol": 0.5 * 10 ** (-d) * k + 1e-9,
                     "pct": bool(pct), "mult": bool(mult)})
    return times, nums


class Facts:
    """Numbers and clock times available from tool results."""

    def __init__(self) -> None:
        self.numbers: set[float] = set()
        self.times: set[tuple[int, int]] = set()

    def add_time(self, h: int, m: int) -> None:
        self.times.add((h % 24, m))
        for v in (h, h % 12 or 12, m):
            self.numbers.add(float(v))

    def add_timestamp(self, s: str) -> None:
        t = parse_utc(s)
        if t is None:
            return
        for tt in (t, t.astimezone(IST)):
            self.add_time(tt.hour, tt.minute)
            self.numbers.update({float(tt.year), float(tt.month), float(tt.day)})

    def add_string(self, s: str) -> None:
        for ts in _ISO_TS.findall(s):
            self.add_timestamp(ts)
        for y, mo, d in _ISO_DATE.findall(s):
            self.numbers.update({float(y), float(mo), float(d)})
        times, nums = extract(s)
        for tm in times:
            self.add_time(tm["h"], tm["m"])
            if tm["ambiguous"]:
                self.add_time(tm["h"] + 12, tm["m"])
        for n in nums:
            self.add_number(n["value"] / 100 if n["pct"] else n["value"])

    def add_number(self, v: float) -> None:
        self.numbers.add(float(v))

    def add(self, obj: Any) -> None:
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, (int, float)):
            self.add_number(obj)
        elif isinstance(obj, str):
            self.add_string(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                self.add(v)
        elif isinstance(obj, (list, tuple)):
            self.add_number(len(obj))
            for v in obj:
                self.add(v)


def _num_ok(n: dict, facts: Iterable[float]) -> bool:
    a, d, tol = n["value"], n["decimals"], n["tol"]
    round_num = d == 0 and not n["mult"] and not n["pct"] and a >= 20 and a % 5 == 0
    for v in facts:
        # a share stored as 0-1 may be written as a percentage; "34%" may also be a share_pct of 34
        for x in ((v, v * 100) if 0 <= v <= 1 else (v,)):
            if abs(a - x) <= tol:
                return True
            if round_num and abs(a - x) <= (5 if a % 10 == 0 and x >= 50 else 2.5):
                return True  # a round number: "about 150" <- 147, "about 75" <- 73.6
    return False


def _time_ok(tm: dict, times: set[tuple[int, int]]) -> bool:
    opts = [tm["h"]] + ([(tm["h"] + 12) % 24] if tm["ambiguous"] else [])
    for h in opts:
        a = h * 60 + tm["m"]
        for th, tmin in times:
            diff = abs(a - (th * 60 + tmin))
            if min(diff, 1440 - diff) <= 30:
                return True
    return False


def check(answer: str, tool_results: list[Any], question: str = "") -> dict:
    """{verified, total, unverified: [raw strings]} for the numbers in `answer`."""
    facts = Facts()
    for r in tool_results:
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except ValueError:
                pass
        facts.add(r)
    q_times, q_nums = extract(question or "")
    q_vals = {n["value"] for n in q_nums} | {float(t["h"]) for t in q_times}
    times, nums = extract(answer)
    seen: set[str] = set()
    verified, total, unverified = 0, 0, []
    for tm in times:
        if tm["raw"] in seen:
            continue
        seen.add(tm["raw"])
        total += 1
        if _time_ok(tm, facts.times):
            verified += 1
        else:
            unverified.append(tm["raw"])
    for n in nums:
        if n["raw"] in seen:
            continue
        seen.add(n["raw"])
        if n["value"] in q_vals:
            continue
        total += 1
        if _num_ok(n, facts.numbers):
            verified += 1
        else:
            unverified.append(n["raw"])
    return {"verified": verified, "total": total, "unverified": unverified}
