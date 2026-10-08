"use client";

import { ThemeProvider, useTheme } from "next-themes";
import { useEffect } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/lib/i18n";
import { playback } from "@/lib/playback";

function ReducedMotionSync() {
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => playback.setReducedMotion(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return null;
}

/** ?theme=dark|light deep link (used for demo recordings and screenshots) */
function ThemeFromQuery() {
  const { setTheme } = useTheme();
  useEffect(() => {
    const v = new URLSearchParams(window.location.search).get("theme");
    if (v === "dark" || v === "light") setTheme(v);
  }, [setTheme]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
      <I18nProvider>
        <TooltipProvider delayDuration={250}>
          <ReducedMotionSync />
          <ThemeFromQuery />
          {children}
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
