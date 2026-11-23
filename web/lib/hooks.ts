"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, get } from "./api";

const cache = new Map<string, unknown>();
const listeners = new Set<() => void>();
let revision = 0;

/** Invalidate every cached GET (after a write). Mounted hooks refetch in the background. */
export function invalidate() {
  revision++;
  listeners.forEach((l) => l());
}

export function clearCache() {
  cache.clear();
  invalidate();
}

/** Stale-while-revalidate GET: cached data renders instantly, fresh data replaces it. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | undefined>(() => (path ? (cache.get(path) as T | undefined) : undefined));
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path && !cache.has(path));
  const [rev, setRev] = useState(revision);
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    const l = () => setRev(revision);
    listeners.add(l);
    return () => {
      live.current = false;
      listeners.delete(l);
    };
  }, []);

  const load = useCallback(async () => {
    if (!path) return;
    if (!cache.has(path)) setLoading(true);
    try {
      const d = await get<T>(path);
      cache.set(path, d);
      if (live.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (live.current) setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      if (live.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (path && cache.has(path)) setData(cache.get(path) as T);
    load();
  }, [load, rev, path]);

  return { data, error, loading, reload: load, setData };
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function usePrefersReducedMotion(): boolean {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setR(m.matches);
    const on = () => setR(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return r;
}

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
}

export function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export const pct = (x: number, digits = 0) => `${(100 * x).toFixed(digits)}%`;
export const n = (x: number | null | undefined) => (x == null ? "—" : x.toLocaleString());
