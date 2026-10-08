"use client";

import { useSyncExternalStore } from "react";
import { H_MAX, H_MIN } from "./time";

/**
 * Global playback clock for the map, scrubber and chart cursor.
 * `minutes` = minutes since t0-24h (0 .. 96*60), the TripsLayer time base.
 * React subscribers read the whole hour; the map reads minutes every frame.
 */
const MAX_MIN = (H_MAX - H_MIN) * 60;

export type Speed = 1 | 4 | 16;
/** model minutes advanced per real second */
const RATE: Record<Speed, number> = { 1: 30, 4: 120, 16: 480 };

interface State {
  minutes: number;
  playing: boolean;
  speed: Speed;
  reducedMotion: boolean;
}

const state: State = { minutes: 24 * 60, playing: false, speed: 4, reducedMotion: false };
const subs = new Set<() => void>();
const frameSubs = new Set<(minutes: number) => void>();
let raf = 0;
let last = 0;
let stepTimer: ReturnType<typeof setInterval> | null = null;
let hiddenPaused = false;

function emit() {
  subs.forEach((s) => s());
}
function emitFrame() {
  frameSubs.forEach((s) => s(state.minutes));
}

function tick(ts: number) {
  if (!state.playing) return;
  const dt = last ? Math.min(0.1, (ts - last) / 1000) : 0;
  last = ts;
  const prevHour = Math.floor(state.minutes / 60);
  state.minutes += dt * RATE[state.speed];
  if (state.minutes >= MAX_MIN) state.minutes = 0; // loop
  emitFrame();
  if (Math.floor(state.minutes / 60) !== prevHour) emit();
  raf = requestAnimationFrame(tick);
}

function start() {
  stop();
  if (state.reducedMotion) {
    // reduced motion: step hour by hour, no continuous animation
    stepTimer = setInterval(() => {
      state.minutes = Math.floor(state.minutes / 60) * 60 + 60;
      if (state.minutes > MAX_MIN) state.minutes = 0;
      emitFrame();
      emit();
    }, 900 / (state.speed === 16 ? 4 : state.speed === 4 ? 2 : 1));
  } else {
    last = 0;
    raf = requestAnimationFrame(tick);
  }
}
function stop() {
  cancelAnimationFrame(raf);
  if (stepTimer) clearInterval(stepTimer);
  stepTimer = null;
}

export const playback = {
  get: () => state,
  setMinutes(m: number) {
    state.minutes = Math.max(0, Math.min(MAX_MIN, m));
    emitFrame();
    emit();
  },
  /** offset hour -24..72 */
  setHour(h: number) {
    playback.setMinutes((h - H_MIN) * 60);
  },
  play() {
    if (state.playing) return;
    state.playing = true;
    start();
    emit();
  },
  pause() {
    state.playing = false;
    stop();
    emit();
  },
  toggle() {
    if (state.playing) playback.pause();
    else playback.play();
  },
  setSpeed(s: Speed) {
    state.speed = s;
    if (state.playing) start();
    emit();
  },
  setReducedMotion(v: boolean) {
    state.reducedMotion = v;
    if (state.playing) start();
    emit();
  },
  onFrame(cb: (minutes: number) => void) {
    frameSubs.add(cb);
    return () => frameSubs.delete(cb);
  },
};

if (typeof document !== "undefined") {
  // pause animation when the tab is hidden; resume when it comes back
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && state.playing) {
      hiddenPaused = true;
      stop();
    } else if (!document.hidden && hiddenPaused) {
      hiddenPaused = false;
      if (state.playing) start();
    }
  });
}

function subscribe(cb: () => void) {
  subs.add(cb);
  return () => subs.delete(cb);
}

/** current offset hour, -24..72 (integer) */
export function useHour(): number {
  return useSyncExternalStore(
    subscribe,
    () => Math.floor(state.minutes / 60) + H_MIN,
    () => 0,
  );
}
export function usePlaying(): boolean {
  return useSyncExternalStore(subscribe, () => state.playing, () => false);
}
export function useSpeed(): Speed {
  return useSyncExternalStore(subscribe, () => state.speed, () => 4 as Speed);
}
export function useReducedMotionFlag(): boolean {
  return useSyncExternalStore(subscribe, () => state.reducedMotion, () => false);
}
