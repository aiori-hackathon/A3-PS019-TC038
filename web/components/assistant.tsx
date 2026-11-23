"use client";

import { Bot, Lock, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { AiText, CharCount, MAX_CHARS, ModelBadge } from "./ai-text";
import { useApp } from "./app-context";
import { useNav } from "./shell";

type Answer = { answer: string; findings: { pt_id: string; label: string }[]; docs: { title: string; href: string }[]; mode: string; model?: string; privacy: string };
type Msg = { me: boolean; text: string; a?: Answer };

export function Assistant() {
  const app = useApp();
  const { openFinding } = useNav();
  const { data: info } = useApi<{ suggestions: string[]; llm: { enabled: boolean; sends: string; provider: string | null; model: string | null } }>("/api/assistant");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setMsgs((m) => [...m, { me: true, text: question }]);
    setQ("");
    setBusy(true);
    try {
      const a = await post<Answer>("/api/assistant", { question });
      setMsgs((m) => [...m, { me: false, text: a.answer, a }]);
    } catch (e) {
      setMsgs((m) => [...m, { me: false, text: (e as Error).message, a: { answer: (e as Error).message, findings: [], docs: [], mode: "error", privacy: "" } }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="assistant card" role="dialog" aria-label="Help assistant">
      <div className="card-head">
        <div className="row" style={{ gap: 8 }}>
          <Bot size={18} color="var(--accent)" />
          <div>
            <h4>Ask AI</h4>
            <div className="small faint row" style={{ gap: 4 }}>
              <Lock size={11} />
              {info?.llm.enabled ? `${info.llm.provider} · ${info.llm.model?.split("/").pop()} · metadata only` : "Offline engine · metadata only"}
            </div>
          </div>
        </div>
        <button className="btn sm icon ghost" onClick={() => app.setAssistant(false)} aria-label="Close assistant"><X size={16} /></button>
      </div>
      <div className="msgs" aria-live="polite">
        {msgs.length === 0 && (
          <>
            <div className="row wrap" style={{ gap: 6 }}>
              {(info?.suggestions ?? []).map((s) => (
                <button key={s} className="suggest" onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          </>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.me ? "me" : ""}`}>
            {m.a ? <><div style={{ marginBottom: 6 }}><ModelBadge mode={m.a.mode} model={m.a.model} /></div><AiText text={m.text} onFinding={openFinding} /></> : m.text}
            {m.a && m.a.mode !== "llm" && m.a.findings.length > 0 && (
              <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                {m.a.findings.map((f) => <button key={f.pt_id} className="suggest mono" onClick={() => openFinding(f.pt_id)}>{f.pt_id} {f.label}</button>)}
              </div>
            )}
            {m.a && m.a.docs.map((d) => <div key={d.href} className="small" style={{ marginTop: 6 }}><a href={d.href}>Read: {d.title}</a></div>)}
          </div>
        ))}
        {busy && <div className="bubble faint">Thinking…</div>}
        <div ref={end} />
      </div>
      <form className="row" style={{ padding: 12, borderTop: "1px solid var(--border)", gap: 8 }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input ref={input} className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Why was customers.mobile flagged?" aria-label="Your question" maxLength={MAX_CHARS} />
        <CharCount n={q.length} />
        <button className="btn icon primary" disabled={busy || q.trim().length < 3 || q.length > MAX_CHARS} aria-label="Send"><Send size={16} /></button>
      </form>
    </section>
  );
}
