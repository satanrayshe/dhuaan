"use client";

import { useState } from "react";
import { ArrowUpIcon, CircleAlertIcon, CircleCheckIcon, RotateCwIcon, WifiOffIcon } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { API_BASE, ask, reload, useHealth } from "@/lib/data";
import { useI18n, type DictKey } from "@/lib/i18n";
import { istTime } from "@/lib/time";
import type { AskResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SectionLabel } from "./bits";

interface Turn {
  id: number;
  question: string;
  at: number;
  status: "pending" | "done" | "error";
  res?: AskResponse;
  error?: string;
}

const SUGGESTIONS: DictKey[] = ["ask.s1", "ask.s2", "ask.s3"];

export function GroundingBadge({ verified, total, unverified }: { verified: number; total: number; unverified?: string[] }) {
  const { t } = useI18n();
  const ok = total === 0 || verified === total;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 font-mono text-[0.7rem]",
        ok ? "border-[#207d44]/40 text-[#1a6b3a] dark:border-[#37b24d]/40 dark:text-[#69db7c]" : "border-destructive/40 text-destructive",
      )}
      title={!ok && unverified?.length ? `${t("ask.unverifiedList")} ${unverified.join(", ")}` : undefined}
    >
      {ok ? <CircleCheckIcon className="size-3" aria-hidden /> : <CircleAlertIcon className="size-3" aria-hidden />}
      {t("ask.verified", { v: verified, t: total })}
    </span>
  );
}

function Answer({ turn }: { turn: Turn }) {
  const { t } = useI18n();
  const r = turn.res!;
  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed whitespace-pre-line">{r.answer}</p>
      <div className="flex flex-wrap items-center gap-2">
        <GroundingBadge verified={r.grounding.verified} total={r.grounding.total} unverified={r.grounding.unverified} />
        <span className="font-mono text-[0.7rem] text-muted-foreground">
          {r.model}
          {r.cached ? ` · ${t("ask.cached")}` : ""} · {istTime(turn.at)}
        </span>
      </div>
      {r.tool_trace.length > 0 && (
        <Accordion type="single" collapsible className="rounded-md border border-border">
          <AccordionItem value="trace" className="border-0">
            <AccordionTrigger className="px-3 py-2 text-xs hover:no-underline">
              {t("ask.trace")} · {r.tool_trace.length}
            </AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <ol className="space-y-2">
                {r.tool_trace.map((tr, i) => (
                  <li key={i} className="grid grid-cols-[1rem_1fr] gap-2 text-xs">
                    <CircleCheckIcon className="mt-0.5 size-3.5 text-muted-foreground" aria-hidden />
                    <div className="min-w-0">
                      <p>{tr.summary}</p>
                      <p className="truncate font-mono text-[0.68rem] text-muted-foreground">
                        {tr.tool}({Object.entries(tr.args ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
    </div>
  );
}

export function AskPanel({ placeId, placeName, className }: { placeId?: string; placeName?: string; className?: string }) {
  const { t, lang } = useI18n();
  const health = useHealth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const offline = health.status === "error" || health.status === "missing";
  const pending = turns.some((x) => x.status === "pending");

  const submit = async (question: string) => {
    const text = question.trim();
    if (!text || pending) return;
    const id = Date.now();
    setQ("");
    setTurns((ts) => [...ts, { id, question: text, at: Date.now(), status: "pending" }]);
    try {
      const res = await ask({ question: text, place_id: placeId, lang });
      setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, status: "done", res, at: Date.now() } : x)));
    } catch (e) {
      setTurns((ts) => ts.map((x) => (x.id === id ? { ...x, status: "error", error: (e as Error).message } : x)));
    }
  };

  const last = turns[turns.length - 1];
  const lastGood = [...turns].reverse().find((x) => x.status === "done");

  return (
    <section aria-labelledby="ask-title" className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <SectionLabel id="ask-title">{t("ask.title")}</SectionLabel>
        {health.status === "ready" && (
          <span className="font-mono text-[0.68rem] text-muted-foreground">{health.data.model_provider}</span>
        )}
      </div>

      {offline ? (
        <div className="flex items-start gap-3 rounded-md border border-dashed border-border p-3 text-sm">
          <WifiOffIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="space-y-2">
            <p className="text-muted-foreground">{t("ask.offline")}</p>
            <Button variant="outline" size="sm" onClick={() => reload(`${API_BASE}/api/health`)}>
              <RotateCwIcon aria-hidden /> {t("ask.retry")}
            </Button>
          </div>
        </div>
      ) : (
        <>
          {turns.length === 0 && (
            <div className="flex flex-col items-start gap-1.5">
              {SUGGESTIONS.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => submit(t(k))}
                  disabled={health.status !== "ready"}
                  className="rounded-md border border-border px-2.5 py-1.5 text-left text-xs transition-colors hover:border-foreground/30 hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-50"
                >
                  {t(k)}
                </button>
              ))}
            </div>
          )}

          {turns.length > 0 && last && (
            <div className="space-y-3" aria-live="polite">
              <p className="rounded-md bg-muted px-3 py-2 text-sm">{last.question}</p>
              {last.status === "pending" && (
                <div className="relative overflow-hidden rounded-md border border-border px-3 py-3">
                  <span className="beam-line absolute inset-x-0 top-0 h-px" aria-hidden />
                  <p className="text-sm text-muted-foreground">{t("ask.thinking")}…</p>
                </div>
              )}
              {last.status === "done" && <Answer turn={last} />}
              {last.status === "error" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2 rounded-md border border-destructive/40 px-3 py-2 text-sm">
                    <span className="text-destructive">{t("ask.error")}</span>
                    <Button variant="outline" size="sm" onClick={() => submit(last.question)}>
                      <RotateCwIcon aria-hidden /> {t("ask.retry")}
                    </Button>
                  </div>
                  {lastGood && (
                    <div className="opacity-80">
                      <p className="mb-1 font-mono text-[0.68rem] text-muted-foreground">
                        {t("ask.lastGood", { time: istTime(lastGood.at) + " IST" })}
                      </p>
                      <Answer turn={lastGood} />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              submit(q);
            }}
          >
            <label htmlFor={`ask-${placeId ?? "any"}`} className="sr-only">
              {t("ask.placeholder")}
            </label>
            <input
              id={`ask-${placeId ?? "any"}`}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={placeName ? `${t("ask.placeholder")} · ${placeName}` : t("ask.placeholder")}
              className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              maxLength={400}
            />
            <Button type="submit" size="icon" className="size-9" disabled={!q.trim() || pending} aria-label={t("ask.send")}>
              <ArrowUpIcon aria-hidden />
            </Button>
          </form>
        </>
      )}
    </section>
  );
}
