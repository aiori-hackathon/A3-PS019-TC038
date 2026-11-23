// API client. Each browser holds a random workspace key (no login); writes carry an
// origin-bound CSRF token fetched from /api/session.

// "same-origin": the API serves this frontend (single-container deployment), so call it relatively.
const CONFIGURED_API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const API_BASE = CONFIGURED_API === "same-origin" ? "" : CONFIGURED_API.replace(/\/$/, "");

const memory = new Map<string, string>();
export const storage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return memory.get(key) ?? null;
    }
  },
  set(key: string, value: string) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      memory.set(key, value);
    }
  },
  remove(key: string) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      memory.delete(key);
    }
  },
};

function randomKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function workspaceKey(): string {
  let k = storage.get("pt.workspace");
  if (!k || !/^[A-Za-z0-9_-]{32,128}$/.test(k)) {
    k = randomKey();
    storage.set("pt.workspace", k);
  }
  return k;
}

export function newWorkspace(): string {
  const k = randomKey();
  storage.set("pt.workspace", k);
  csrf = null;
  return k;
}

export function actor(): string {
  return storage.get("pt.actor") || "reviewer";
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let csrf: string | null = null;
let sessionPromise: Promise<Session> | null = null;

export type Session = {
  csrf: string;
  version: string;
  disclaimer: string;
  workspace: { name: string; settings: Record<string, unknown>; created_at: string; scans: number };
  llm: { enabled: boolean; endpoint: string | null; sends: string };
  limits: { csv_mb: number; sqlite_mb: number; sample_sizes: number[]; strategies: string[]; default_sample: number };
};

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { "X-Workspace-Key": workspaceKey(), "X-Actor": actor(), ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...extra };
}

export async function health(timeoutMs = 4000): Promise<boolean> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: ctl.signal, cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

export function session(force = false): Promise<Session> {
  if (!sessionPromise || force) {
    sessionPromise = raw<Session>("GET", "/api/session").then((s) => {
      csrf = s.csrf;
      return s;
    });
    sessionPromise.catch(() => (sessionPromise = null));
  }
  return sessionPromise;
}

async function parseError(r: Response): Promise<ApiError> {
  let detail = `Request failed (${r.status})`;
  let code: string | undefined;
  try {
    const j = await r.json();
    detail = typeof j.detail === "string" ? j.detail : detail;
    code = j.code;
  } catch {
    /* not JSON */
  }
  return new ApiError(detail, r.status, code);
}

async function raw<T>(method: string, path: string, body?: unknown, isForm = false): Promise<T> {
  const init: RequestInit = { method, headers: headers(isForm || body === undefined ? {} : { "Content-Type": "application/json" }) };
  if (body !== undefined) init.body = isForm ? (body as FormData) : JSON.stringify(body);
  let r: Response;
  try {
    r = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the PrivacyTwin server. Check your connection and retry.", 0, "network");
  }
  if (!r.ok) throw await parseError(r);
  const type = r.headers.get("content-type") || "";
  return (type.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export async function api<T = unknown>(method: string, path: string, body?: unknown, isForm = false): Promise<T> {
  if (method !== "GET" && !csrf) await session();
  try {
    return await raw<T>(method, path, body, isForm);
  } catch (e) {
    if (e instanceof ApiError && e.code === "csrf") {
      await session(true);
      return raw<T>(method, path, body, isForm);
    }
    throw e;
  }
}

export const get = <T = unknown>(path: string) => api<T>("GET", path);
export const post = <T = unknown>(path: string, body?: unknown) => api<T>("POST", path, body ?? {});
export const put = <T = unknown>(path: string, body?: unknown) => api<T>("PUT", path, body ?? {});

export async function upload<T = unknown>(path: string, file: File | Blob, fields: Record<string, string> = {}, name = "file.bin"): Promise<T> {
  const fd = new FormData();
  fd.append("file", file, (file as File).name || name);
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  return api<T>("POST", path, fd, true);
}

/** Download a file from the API (GET or POST) and hand it to the browser. */
export async function download(path: string, method: "GET" | "POST" = "GET", form?: FormData): Promise<Response> {
  if (method === "POST" && !csrf) await session();
  const go = () => fetch(`${API_BASE}${path}`, { method, headers: headers(), body: form });
  let r = await go().catch(() => null);
  if (r && r.status === 403) {
    await session(true);
    r = await go().catch(() => null);
  }
  if (!r) throw new ApiError("Cannot reach the PrivacyTwin server.", 0, "network");
  if (!r.ok) throw await parseError(r);
  const blob = await r.clone().blob();
  const cd = r.headers.get("content-disposition") || "";
  const filename = /filename="([^"]+)"/.exec(cd)?.[1] || "privacytwin-download";
  saveBlob(blob, filename);
  return r;
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export type ScanEvent =
  | { type: "reading"; file: string; kind: string; bytes?: number }
  | { type: "start"; source_id: string; source: string; kind: string; tables: number; columns: number; rescan: boolean; ruleset: string }
  | { type: "table"; table: string; columns: number; rows_sampled: number; total_rows: number }
  | { type: "column"; progress: number; table: string; column: string; class: string; confidence: number; band: string; pt_id: string | null; masked_examples: string[] }
  | { type: "triage"; detail: string }
  | { type: "done"; scan_id: string; scan_seq: number; source_id: string; summary: { tables: number; columns: number; personal: number; by_class: Record<string, number> }; receipt: Record<string, unknown>; auto_triage?: { approved: number; batch_id: string | null; status: string } | null }
  | { type: "error"; detail: string };

/** POST a scan and stream NDJSON progress events. */
export async function streamScan(path: string, body: FormData | object, onEvent: (e: ScanEvent) => void): Promise<void> {
  if (!csrf) await session();
  const isForm = body instanceof FormData;
  const go = () =>
    fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: headers(isForm ? {} : { "Content-Type": "application/json" }),
      body: isForm ? (body as FormData) : JSON.stringify(body),
    });
  let r = await go().catch(() => null);
  if (r && r.status === 403) {
    await session(true);
    r = await go().catch(() => null);
  }
  if (!r) throw new ApiError("Cannot reach the PrivacyTwin server.", 0, "network");
  if (!r.ok || !r.body) throw await parseError(r);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}
