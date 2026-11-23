"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, post, streamScan, storage, type ScanEvent } from "@/lib/api";
import { invalidate } from "@/lib/hooks";

export type Toast = { id: number; text: string; kind?: "info" | "error" | "ok"; undo?: () => Promise<unknown> | void; ms: number };
export type ScanState = {
  active: boolean;
  file: string;
  progress: number;
  events: ScanEvent[];
  error: string | null;
  done: Extract<ScanEvent, { type: "done" }> | null;
};
export type ScanOptions = { sample_size: number; strategy: string };

type Ctx = {
  toast: (text: string, opts?: { undo?: Toast["undo"]; kind?: Toast["kind"]; ms?: number }) => void;
  toasts: Toast[];
  dismiss: (id: number) => void;
  saved: number;
  markSaved: () => void;
  scan: ScanState;
  startScan: (file: File, opts?: Partial<ScanOptions>) => Promise<void>;
  startPostgres: (dsn: string, name: string, opts?: Partial<ScanOptions>) => Promise<void>;
  closeScan: () => void;
  scanOptions: ScanOptions;
  setScanOptions: (o: ScanOptions) => void;
  palette: boolean;
  setPalette: (b: boolean) => void;
  help: boolean;
  setHelp: (b: boolean) => void;
  assistant: boolean;
  setAssistant: (b: boolean) => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
  demoLoading: boolean;
  loadDemo: () => Promise<void>;
};

const AppCtx = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}

const EMPTY_SCAN: ScanState = { active: false, file: "", progress: 0, events: [], error: null, done: null };

export function AppProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [saved, setSaved] = useState(0);
  const [scan, setScan] = useState<ScanState>(EMPTY_SCAN);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [assistant, setAssistant] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [scanOptions, setScanOptionsState] = useState<ScanOptions>({ sample_size: 1000, strategy: "random" });
  const nextId = useRef(1);

  useEffect(() => {
    setTheme((document.documentElement.dataset.theme as "dark" | "light") || "dark");
    const saved = storage.get("pt.scanOptions");
    if (saved) {
      try {
        setScanOptionsState(JSON.parse(saved));
      } catch {
        /* ignore */
      }
    }
  }, []);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback<Ctx["toast"]>(
    (text, opts = {}) => {
      const id = nextId.current++;
      const ms = opts.ms ?? (opts.undo ? 5000 : 3500);
      setToasts((t) => [...t.slice(-3), { id, text, kind: opts.kind, undo: opts.undo, ms }]);
      setTimeout(() => dismiss(id), ms);
    },
    [dismiss],
  );
  const markSaved = useCallback(() => setSaved(Date.now()), []);

  const setScanOptions = useCallback((o: ScanOptions) => {
    setScanOptionsState(o);
    storage.set("pt.scanOptions", JSON.stringify(o));
  }, []);

  const run = useCallback(
    async (label: string, path: string, body: FormData | object) => {
      setScan({ ...EMPTY_SCAN, active: true, file: label });
      try {
        await streamScan(path, body, (e) => {
          setScan((s) => ({
            ...s,
            events: e.type === "column" || e.type === "table" || e.type === "start" || e.type === "reading" || e.type === "triage" ? [...s.events.slice(-400), e] : s.events,
            progress: e.type === "column" ? e.progress : e.type === "done" ? 1 : s.progress,
            done: e.type === "done" ? e : s.done,
            error: e.type === "error" ? e.detail : s.error,
          }));
          if (e.type === "done") {
            invalidate();
            toast(`Scan #${e.scan_seq} complete: ${e.summary.personal} personal-data candidates in ${e.summary.columns} columns`, { kind: "ok" });
            if (e.auto_triage?.batch_id) {
              const batch = e.auto_triage.batch_id;
              toast(`${e.auto_triage.approved} candidates auto-approved by AI`, {
                undo: () => post("/api/auto-triage/undo", { batch_id: batch }),
              });
            } else if (e.auto_triage?.status === "unavailable") {
              toast("Scan saved. AI auto-triage unavailable; candidates remain for review.");
            }
          }
        });
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "The scan could not be started.";
        setScan((s) => ({ ...s, error: msg }));
      }
    },
    [toast],
  );

  const startScan = useCallback(
    async (file: File, opts?: Partial<ScanOptions>) => {
      const o = { ...scanOptions, ...opts };
      const fd = new FormData();
      fd.append("file", file, file.name);
      fd.append("sample_size", String(o.sample_size));
      fd.append("strategy", o.strategy);
      await run(file.name, "/api/scan", fd);
    },
    [run, scanOptions],
  );

  const startPostgres = useCallback(
    async (dsn: string, name: string, opts?: Partial<ScanOptions>) => {
      const o = { ...scanOptions, ...opts };
      await run(name, "/api/scan/postgres", { dsn, name, sample_size: o.sample_size, strategy: o.strategy });
    },
    [run, scanOptions],
  );

  const [demoLoading, setDemoLoading] = useState(false);
  const loadDemo = useCallback(async () => {
    setDemoLoading(true);
    try {
      const r = await post<{ loaded: boolean }>("/api/demo", {});
      invalidate();
      toast(r.loaded ? "Demo company loaded: Acme Fintech India (synthetic), 3 scans" : "The demo is already loaded in this workspace", { kind: "ok" });
    } catch (e) {
      toast((e as Error).message, { kind: "error" });
    } finally {
      setDemoLoading(false);
    }
  }, [toast]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      storage.set("pt.theme", next);
      return next;
    });
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      toast, toasts, dismiss, saved, markSaved, scan, startScan, startPostgres, closeScan: () => setScan(EMPTY_SCAN),
      scanOptions, setScanOptions, palette, setPalette, help, setHelp, assistant, setAssistant, theme, toggleTheme, demoLoading, loadDemo,
    }),
    [toast, toasts, dismiss, saved, markSaved, scan, startScan, startPostgres, scanOptions, setScanOptions, palette, help, assistant, theme, toggleTheme, demoLoading, loadDemo],
  );
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
