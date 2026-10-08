"use client";

import { useI18n } from "@/lib/i18n";
import type { Lang } from "@/lib/types";

type Box = { id: string; x: number; y: number; w: number; h: number; title: string; sub?: string; kind?: "aws" | "ext" | "app" };

const BOXES: Box[] = [
  { id: "firms", x: 10, y: 120, w: 180, h: 46, title: "NASA FIRMS", sub: "VIIRS · MODIS fires", kind: "ext" },
  { id: "lsa", x: 10, y: 176, w: 180, h: 46, title: "LSA SAF", sub: "MSG-IODC evening FRP", kind: "ext" },
  { id: "meteo", x: 10, y: 232, w: 180, h: 46, title: "Open-Meteo", sub: "GFS winds · BLH", kind: "ext" },
  { id: "aq", x: 10, y: 288, w: 180, h: 46, title: "OpenAQ", sub: "CPCB PM2.5", kind: "ext" },
  { id: "sched", x: 300, y: 10, w: 240, h: 50, title: "EventBridge Scheduler", sub: "every 3 h", kind: "aws" },
  { id: "ingest", x: 262, y: 150, w: 112, h: 56, title: "Ingest", sub: "Lambda", kind: "aws" },
  { id: "model", x: 392, y: 150, w: 112, h: 56, title: "Model", sub: "Lambda · numpy", kind: "aws" },
  { id: "advise", x: 522, y: 150, w: 112, h: 56, title: "Advise", sub: "Lambda · rules", kind: "aws" },
  { id: "notify", x: 652, y: 150, w: 112, h: 56, title: "Notify", sub: "Lambda", kind: "aws" },
  { id: "tg", x: 820, y: 150, w: 170, h: 56, title: "Telegram", sub: "06:30 school alert", kind: "ext" },
  { id: "s3", x: 262, y: 300, w: 180, h: 56, title: "Amazon S3", sub: "latest/ artifacts", kind: "aws" },
  { id: "cf", x: 492, y: 300, w: 180, h: 56, title: "CloudFront", sub: "cached JSON", kind: "aws" },
  { id: "web", x: 722, y: 300, w: 268, h: 56, title: "Amplify Hosting", sub: "this app · Next.js static", kind: "app" },
  { id: "llm", x: 262, y: 420, w: 180, h: 56, title: "Gemini / Bedrock Nova", sub: "MODEL_PROVIDER switch", kind: "aws" },
  { id: "agent", x: 492, y: 420, w: 180, h: 56, title: "Strands agent", sub: "tools · number check", kind: "aws" },
  { id: "fn", x: 722, y: 420, w: 268, h: 56, title: "Lambda Function URL", sub: "/api/ask · search · advisory", kind: "aws" },
  { id: "ddb", x: 722, y: 504, w: 268, h: 46, title: "DynamoDB", sub: "rate limits · answer cache", kind: "aws" },
];

const b = (id: string) => BOXES.find((x) => x.id === id)!;
const right = (id: string): [number, number] => { const x = b(id); return [x.x + x.w, x.y + x.h / 2]; };
const left = (id: string): [number, number] => { const x = b(id); return [x.x, x.y + x.h / 2]; };
const top = (id: string): [number, number] => { const x = b(id); return [x.x + x.w / 2, x.y]; };
const bottom = (id: string): [number, number] => { const x = b(id); return [x.x + x.w / 2, x.y + x.h]; };

const ARROWS: { d: string; dashed?: boolean; label?: [number, number, string] }[] = [
  { d: `M${bottom("sched")[0]} ${bottom("sched")[1]} V 112`, label: [430, 96, "starts"] },
  ...["firms", "lsa", "meteo", "aq"].map((id) => ({ d: `M${right(id)[0]} ${right(id)[1]} H 222 V ${left("ingest")[1]} H ${left("ingest")[0]}` })),
  { d: `M${right("ingest")[0]} ${right("ingest")[1]} H ${left("model")[0]}` },
  { d: `M${right("model")[0]} ${right("model")[1]} H ${left("advise")[0]}` },
  { d: `M${right("advise")[0]} ${right("advise")[1]} H ${left("notify")[0]}` },
  { d: `M${right("notify")[0]} ${right("notify")[1]} H ${left("tg")[0]}` },
  { d: `M${bottom("model")[0]} ${bottom("model")[1]} V 256 H ${top("s3")[0]} V ${top("s3")[1]}`, label: [360, 276, "writes"] },
  { d: `M${right("s3")[0]} ${right("s3")[1]} H ${left("cf")[0]}` },
  { d: `M${right("cf")[0]} ${right("cf")[1]} H ${left("web")[0]}` },
  { d: `M${bottom("web")[0]} ${bottom("web")[1]} V ${top("fn")[1]}`, label: [866, 394, "Ask Dhuaan"] },
  { d: `M${left("fn")[0]} ${left("fn")[1]} H ${right("agent")[0]}` },
  { d: `M${left("agent")[0]} ${left("agent")[1]} H ${right("llm")[0]}` },
  { d: `M${top("agent")[0]} ${top("agent")[1]} V 388 H ${bottom("s3")[0] + 40} V ${bottom("s3")[1]}`, dashed: true, label: [520, 382, "reads forecast"] },
  { d: `M${bottom("fn")[0]} ${bottom("fn")[1]} V ${top("ddb")[1]}` },
];

const STEPS: Record<Lang, { t: string; d: string }[]> = {
  en: [
    { t: "Detect", d: "Fire pixels from the 13:30 VIIRS/MODIS passes, plus evening detections from the geostationary Meteosat-IODC, clustered into burning fields and labelled by sensor." },
    { t: "Transport", d: "Each cluster releases particles weighted by fire power. They ride hourly winds inside the mixed layer for 72 hours, five times over with perturbed winds, so the spread becomes the uncertainty band." },
    { t: "Score", d: "Smoke is summed at every village, school and ward, divided by the boundary-layer depth, which is why nights get worse. Each particle remembers its fire, so every place gets an exact source split and every fire gets a people × hours exposure score." },
    { t: "Advise", d: "Deterministic rules turn forecast PM2.5 into a school-day go/no-go. An agent writes the parent notice in Punjabi, Hindi and English, and every number it states is checked against its tool results." },
  ],
  hi: [
    { t: "पहचान", d: "13:30 के VIIRS/MODIS पास और शाम के भूस्थिर Meteosat-IODC से आग के पिक्सेल, जलते खेतों में समूहित और सेंसर के अनुसार चिह्नित।" },
    { t: "बहाव", d: "हर समूह आग की शक्ति के अनुपात में कण छोड़ता है। वे 72 घंटे तक मिश्रित परत की हवाओं में बहते हैं, पाँच बार बदली हवाओं के साथ, ताकि फैलाव अनिश्चितता बने।" },
    { t: "अंक", d: "हर गाँव, स्कूल और वार्ड पर धुआँ जोड़ा जाता है और सीमा परत की गहराई से भाग दिया जाता है, इसलिए रातें खराब होती हैं। हर कण अपनी आग याद रखता है, इसलिए हर जगह का स्रोत और हर आग का जन-संपर्क अंक मिलता है।" },
    { t: "सलाह", d: "निश्चित नियम पूर्वानुमानित PM2.5 को स्कूल दिवस की हाँ/ना में बदलते हैं। एजेंट पंजाबी, हिंदी और अंग्रेज़ी में अभिभावक सूचना लिखता है, और उसकी हर संख्या टूल परिणामों से जाँची जाती है।" },
  ],
  pa: [
    { t: "ਪਛਾਣ", d: "13:30 ਦੇ VIIRS/MODIS ਪਾਸ ਅਤੇ ਸ਼ਾਮ ਦੇ ਭੂ-ਸਥਿਰ Meteosat-IODC ਤੋਂ ਅੱਗ ਦੇ ਪਿਕਸਲ, ਸੜਦੇ ਖੇਤਾਂ ਵਿੱਚ ਸਮੂਹਿਤ ਅਤੇ ਸੈਂਸਰ ਅਨੁਸਾਰ ਨਿਸ਼ਾਨਬੱਧ।" },
    { t: "ਵਹਾਅ", d: "ਹਰ ਸਮੂਹ ਅੱਗ ਦੀ ਤਾਕਤ ਅਨੁਸਾਰ ਕਣ ਛੱਡਦਾ ਹੈ। ਉਹ 72 ਘੰਟੇ ਮਿਸ਼ਰਤ ਪਰਤ ਦੀਆਂ ਹਵਾਵਾਂ ਵਿੱਚ ਵਹਿੰਦੇ ਹਨ, ਪੰਜ ਵਾਰ ਬਦਲੀਆਂ ਹਵਾਵਾਂ ਨਾਲ, ਤਾਂ ਜੋ ਫੈਲਾਅ ਅਨਿਸ਼ਚਿਤਤਾ ਬਣੇ।" },
    { t: "ਅੰਕ", d: "ਹਰ ਪਿੰਡ, ਸਕੂਲ ਅਤੇ ਵਾਰਡ 'ਤੇ ਧੂੰਆਂ ਜੋੜਿਆ ਜਾਂਦਾ ਹੈ ਅਤੇ ਸੀਮਾ ਪਰਤ ਦੀ ਡੂੰਘਾਈ ਨਾਲ ਵੰਡਿਆ ਜਾਂਦਾ ਹੈ, ਇਸ ਲਈ ਰਾਤਾਂ ਮਾੜੀਆਂ ਹੁੰਦੀਆਂ ਹਨ। ਹਰ ਕਣ ਆਪਣੀ ਅੱਗ ਯਾਦ ਰੱਖਦਾ ਹੈ, ਇਸ ਲਈ ਹਰ ਥਾਂ ਦਾ ਸਰੋਤ ਅਤੇ ਹਰ ਅੱਗ ਦਾ ਜਨ-ਸੰਪਰਕ ਅੰਕ ਮਿਲਦਾ ਹੈ।" },
    { t: "ਸਲਾਹ", d: "ਨਿਸ਼ਚਿਤ ਨਿਯਮ ਭਵਿੱਖਬਾਣੀ PM2.5 ਨੂੰ ਸਕੂਲ ਦਿਨ ਦੀ ਹਾਂ/ਨਾਂਹ ਵਿੱਚ ਬਦਲਦੇ ਹਨ। ਏਜੰਟ ਪੰਜਾਬੀ, ਹਿੰਦੀ ਅਤੇ ਅੰਗਰੇਜ਼ੀ ਵਿੱਚ ਮਾਪਿਆਂ ਦੀ ਸੂਚਨਾ ਲਿਖਦਾ ਹੈ, ਅਤੇ ਉਸਦਾ ਹਰ ਅੰਕ ਟੂਲ ਨਤੀਜਿਆਂ ਨਾਲ ਜਾਂਚਿਆ ਜਾਂਦਾ ਹੈ।" },
  ],
};

export function ArchitectureDiagram() {
  return (
    <figure>
      <div className="overflow-x-auto rounded-lg border border-border bg-card p-3 sm:p-5">
        <svg viewBox="0 0 1000 560" className="h-auto w-full min-w-[720px]" role="img" aria-labelledby="arch-title arch-desc">
          <title id="arch-title">Dhuaan architecture on AWS</title>
          <desc id="arch-desc">
            EventBridge Scheduler starts a Step Functions state machine every three hours. Its four Lambda steps are Ingest, Model, Advise and Notify.
            Ingest reads NASA FIRMS, LSA SAF, Open-Meteo and OpenAQ. Model writes forecast artifacts to Amazon S3, served through CloudFront to this
            app on Amplify Hosting. Notify sends the school alert to Telegram. Questions from the app go to a Lambda Function URL, which runs a Strands
            agent on Gemini or Amazon Bedrock Nova; the agent reads the forecast from S3, and DynamoDB holds rate limits and an answer cache.
          </desc>
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--muted-foreground)" />
            </marker>
          </defs>
          {/* Step Functions container */}
          <rect x="244" y="112" width="538" height="120" rx="8" fill="none" stroke="var(--foreground)" strokeOpacity="0.5" strokeDasharray="5 4" />
          <text x="256" y="134" fontSize="13" fontWeight="600" fill="var(--foreground)">AWS Step Functions</text>
          <text x="400" y="134" fontSize="11" fill="var(--muted-foreground)" fontFamily="var(--font-geist-mono)">one run ≈ 5 transitions, retries per step</text>
          {ARROWS.map((a, i) => (
            <g key={i}>
              <path d={a.d} fill="none" stroke="var(--muted-foreground)" strokeWidth="1.4" strokeDasharray={a.dashed ? "4 4" : undefined} markerEnd="url(#arrow)" />
              {a.label && (
                <text x={a.label[0]} y={a.label[1]} fontSize="10.5" fill="var(--muted-foreground)" fontFamily="var(--font-geist-mono)">
                  {a.label[2]}
                </text>
              )}
            </g>
          ))}
          {BOXES.map((bx) => (
            <g key={bx.id}>
              <rect
                x={bx.x}
                y={bx.y}
                width={bx.w}
                height={bx.h}
                rx="6"
                fill={bx.kind === "app" ? "var(--smoke-soft)" : "var(--background)"}
                stroke={bx.kind === "app" ? "var(--smoke)" : bx.kind === "ext" ? "var(--border)" : "var(--foreground)"}
                strokeOpacity={bx.kind === "aws" ? 0.55 : 1}
                strokeWidth={bx.kind === "app" ? 1.8 : 1.2}
                strokeDasharray={bx.kind === "ext" ? "3 3" : undefined}
              />
              <text x={bx.x + 12} y={bx.y + (bx.sub ? 21 : bx.h / 2 + 5)} fontSize="13" fontWeight="600" fill="var(--foreground)">
                {bx.title}
              </text>
              {bx.sub && (
                <text x={bx.x + 12} y={bx.y + 38} fontSize="11" fill="var(--muted-foreground)" fontFamily="var(--font-geist-mono)">
                  {bx.sub}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-5 rounded-[3px] border border-foreground/55" aria-hidden /> AWS service
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-5 rounded-[3px] border border-dashed border-border" aria-hidden /> External data or channel
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-5 rounded-[3px] border-[1.5px] border-smoke bg-smoke-soft" aria-hidden /> This app
        </span>
        <span>Region ap-south-1 · one SAM template · AWS Free plan</span>
      </figcaption>
    </figure>
  );
}

export function HowView() {
  const { t, lang } = useI18n();
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:py-12">
      <header className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("how.title")}</h1>
        <p className="mt-2 text-muted-foreground">{t("how.subtitle")}</p>
      </header>
      <section aria-labelledby="arch" className="mt-10">
        <h2 id="arch" className="label-mono">
          {t("how.arch")}
        </h2>
        <div className="mt-3">
          <ArchitectureDiagram />
        </div>
      </section>
      <section aria-labelledby="method" className="mt-14">
        <h2 id="method" className="label-mono">
          {t("how.method")}
        </h2>
        <ol className="mt-4 grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2 lg:grid-cols-4">
          {STEPS[lang].map((s, i) => (
            <li key={i} className="bg-background p-5">
              <p className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</p>
              <h3 className="mt-2 text-lg font-semibold">{s.t}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.d}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
