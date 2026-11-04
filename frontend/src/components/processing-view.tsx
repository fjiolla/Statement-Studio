"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileText, KeyRound, Loader2, RotateCcw, ScanLine, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiError, type ProgressEvent, type Statement } from "@/lib/api";
import { cn } from "@/lib/format";
import { LottieAnim } from "./lottie";
import { Button } from "./ui";

const STAGES = [
  { id: "open", label: "Opening & validating PDF" },
  { id: "detect", label: "Detecting page types" },
  { id: "ocr", label: "Reading scanned pages (OCR)" },
  { id: "parse", label: "Rebuilding transaction tables" },
  { id: "reconcile", label: "Reconciling running balances" },
  { id: "classify", label: "Classifying transactions" },
] as const;
const ORDER: Record<string, number> = { queued: -1, open: 0, detect: 1, ocr: 2, ocr_done: 2, parse: 3, reconcile: 4, classify: 5, done: 6 };

type PageState = { kind?: string; ocr?: "running" | "done"; confidence?: number; seconds?: number };

export function ProcessingView({ statement, onDone }: { statement: Statement; onDone: () => void }) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [terminal, setTerminal] = useState<ProgressEvent | null>(
    statement.status === "needs_password" || statement.status === "failed"
      ? { stage: statement.status, message: statement.error ?? "", code: statement.error_code ?? undefined }
      : null,
  );
  const [celebrate, setCelebrate] = useState(false);
  const started = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (terminal) return;
    const es = new EventSource(api.eventsUrl(statement.id));
    es.onmessage = (m) => {
      const ev: ProgressEvent = JSON.parse(m.data);
      if (ev.stage === "heartbeat") return;
      setEvents((prev) => [...prev, ev]);
      if (ev.stage === "done") {
        es.close();
        setCelebrate(true);
        setTimeout(onDone, 1300);
      } else if (ev.stage === "failed" || ev.stage === "needs_password") {
        es.close();
        setTerminal(ev);
      }
    };
    es.onerror = () => {
      // the server closes the stream after a terminal event; a real drop falls back to polling
      es.close();
      setTimeout(onDone, 1500);
    };
    return () => es.close();
  }, [statement.id, terminal, onDone]);

  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - started.current) / 1000), 250);
    return () => clearInterval(t);
  }, []);

  const { current, pages, total, hasOcr, ocrDone } = useMemo(() => {
    let current = -1;
    const pages: Record<number, PageState> = {};
    let total = statement.page_count ?? 0;
    let hasOcr = false;
    let ocrDone = 0;
    for (const e of events) {
      current = Math.max(current, ORDER[e.stage] ?? current);
      if (e.total) total = e.total;
      if (e.page !== undefined) {
        const p = (pages[e.page] ??= {});
        if (e.stage === "detect") p.kind = e.kind;
        if (e.stage === "ocr") {
          p.ocr = "running";
          hasOcr = true;
        }
        if (e.stage === "ocr_done") {
          p.ocr = "done";
          p.confidence = e.confidence;
          p.seconds = e.seconds;
          ocrDone += 1;
        }
      }
    }
    return { current, pages, total, hasOcr, ocrDone };
  }, [events, statement.page_count]);

  const scannedCount = Object.values(pages).filter((p) => p.kind === "scanned").length;
  const last = events[events.length - 1];

  if (terminal?.stage === "needs_password") return <PasswordGate statement={statement} event={terminal} onSubmitted={() => { setTerminal(null); setEvents([]); }} />;
  if (terminal?.stage === "failed") return <Failed statement={statement} event={terminal} />;

  return (
    <div className="mx-auto max-w-[880px] px-4 py-12 sm:px-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card overflow-hidden">
        <div className="grid gap-0 md:grid-cols-[300px_1fr]">
          <div className="relative flex flex-col items-center justify-center border-b border-line bg-surface-2 px-6 py-8 md:border-b-0 md:border-r">
            <div className="h-44 w-44">
              <AnimatePresence mode="wait">
                {celebrate ? (
                  <motion.div key="ok" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="h-full w-full">
                    <LottieAnim name="success" loop={false} className="h-full w-full" fallback={<Check className="m-auto mt-14 h-14 w-14 text-pos" />} />
                  </motion.div>
                ) : (
                  <motion.div key="scan" exit={{ opacity: 0, scale: 0.95 }} className="h-full w-full">
                    <LottieAnim name="scanning" className="h-full w-full" fallback={<Loader2 className="m-auto mt-14 h-12 w-12 animate-spin text-accent" />} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <p className="mt-2 max-w-[220px] truncate text-center text-sm font-medium text-ink" title={statement.filename}>{statement.filename}</p>
            <p className="num mt-1 text-xs text-muted">{celebrate ? "Ready" : `${elapsed.toFixed(0)}s elapsed`}</p>
          </div>
          <div className="p-6 sm:p-8">
            <h1 className="text-lg font-semibold tracking-tight text-ink">{celebrate ? "Statement ready" : "Processing your statement"}</h1>
            <p className="mt-1 h-5 truncate text-sm text-ink-2">{celebrate ? `${last?.transactions ?? ""} transactions extracted and checked.` : last?.message ?? "Queued…"}</p>
            <ol className="mt-6 space-y-1">
              {STAGES.map((s, i) => {
                if (s.id === "ocr" && !hasOcr && current > 2) return null;
                const state = celebrate || current > i ? "done" : current === i ? "active" : "todo";
                return (
                  <li key={s.id} className="flex items-center gap-3 py-1.5">
                    <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-colors duration-300",
                      state === "done" && "border-transparent bg-pos-soft text-pos",
                      state === "active" && "border-accent bg-accent-soft text-accent",
                      state === "todo" && "border-line text-muted")}>
                      {state === "done" ? <Check className="h-3.5 w-3.5" /> : state === "active" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                    </span>
                    <span className={cn("text-sm transition-colors", state === "todo" ? "text-muted" : "text-ink")}>{s.label}</span>
                    {s.id === "ocr" && hasOcr && scannedCount > 0 && (
                      <span className="num ml-auto text-xs text-muted">{ocrDone}/{scannedCount} pages</span>
                    )}
                  </li>
                );
              })}
            </ol>
            {hasOcr && scannedCount > 0 && !celebrate && (
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-3">
                <motion.div className="h-full rounded-full bg-accent" animate={{ width: `${(ocrDone / scannedCount) * 100}%` }} />
              </div>
            )}
            {total > 0 && (
              <div className="mt-6">
                <p className="mb-2 text-xs text-muted">Pages</p>
                <div className="flex flex-wrap gap-1.5">
                  {Array.from({ length: total }).map((_, i) => {
                    const p = pages[i];
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: p?.kind ? 1 : 0.45, scale: 1 }}
                        transition={{ delay: i * 0.015 }}
                        title={p?.kind ? `Page ${i + 1}: ${p.kind === "scanned" ? "scanned" : "text"}${p.confidence ? ` · OCR ${(p.confidence * 100).toFixed(0)}%` : ""}` : `Page ${i + 1}`}
                        className={cn("relative flex h-10 w-8 flex-col items-center justify-center rounded-[5px] border text-[9px] font-medium",
                          !p?.kind && "border-line bg-surface-2 text-muted",
                          p?.kind && p.kind !== "scanned" && "border-line bg-surface text-ink-2",
                          p?.kind === "scanned" && "border-accent/40 bg-accent-soft text-accent-ink")}
                      >
                        {p?.kind === "scanned" ? <ScanLine className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                        <span className="num mt-0.5">{i + 1}</span>
                        {p?.ocr === "running" && <span className="absolute inset-0 rounded-[5px] shimmer" />}
                      </motion.div>
                    );
                  })}
                </div>
                <p className="mt-2 flex gap-4 text-[11px] text-muted">
                  <span className="flex items-center gap-1"><FileText className="h-3 w-3" /> Text layer</span>
                  <span className="flex items-center gap-1"><ScanLine className="h-3 w-3" /> Scanned → OCR</span>
                </p>
              </div>
            )}
          </div>
        </div>
      </motion.div>
      {hasOcr && !celebrate && (
        <p className="mt-4 text-center text-xs text-muted">Scanned pages take a few seconds each.</p>
      )}
    </div>
  );
}

function PasswordGate({ statement, event, onSubmitted }: { statement: Statement; event: ProgressEvent; onSubmitted: () => void }) {
  const qc = useQueryClient();
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const wrong = event.code === "invalid_password";
  const submit = useMutation({
    mutationFn: () => api.password(statement.id, pw),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["statement", statement.id] });
      onSubmitted();
    },
  });
  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <motion.form
        initial={{ opacity: 0, y: 10 }}
        animate={wrong ? { opacity: 1, y: 0, x: [0, -8, 8, -5, 5, 0] } : { opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        onSubmit={(e) => { e.preventDefault(); if (pw) submit.mutate(); }}
        className="card p-7"
      >
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-warn-soft text-warn"><KeyRound className="h-5 w-5" /></span>
        <h1 className="mt-4 text-lg font-semibold tracking-tight text-ink">This statement is password protected</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
          Often your date of birth (DDMMYYYY), PAN or customer ID. It&apos;s never stored.
        </p>
        <div className="mt-5">
          <label htmlFor="pw" className="text-xs font-medium text-ink-2">Password</label>
          <div className={cn("mt-1.5 flex h-11 items-center gap-3 rounded-lg border bg-surface pl-3 pr-1.5 transition-colors focus-within:border-accent", wrong ? "border-crit" : "border-line")}>
            <input id="pw" autoFocus type={show ? "text" : "password"} value={pw} onChange={(e) => setPw(e.target.value)} className="h-full min-w-0 flex-1 bg-transparent text-sm text-ink outline-none" autoComplete="off" spellCheck={false} />
            <button type="button" onClick={() => setShow((s) => !s)} className="shrink-0 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-ink-2">{show ? "Hide" : "Show"}</button>
          </div>
          {wrong && <p className="mt-2 text-xs text-crit">That password didn&apos;t work. Check the format your bank uses and try again.</p>}
          {submit.isError && <p className="mt-2 text-xs text-crit">{(submit.error as ApiError).message}</p>}
        </div>
        <Button type="submit" variant="primary" className="mt-5 w-full" loading={submit.isPending} disabled={!pw}>Unlock & process</Button>
      </motion.form>
    </div>
  );
}

const FAIL_HINTS: Record<string, string> = {
  not_a_pdf: "Upload the statement as a PDF downloaded from your bank.",
  no_transactions: "We couldn't find a transaction table. Make sure this is an account or card statement, not a summary or advice.",
  corrupt_pdf: "The file is damaged. Download it again from your bank and retry.",
  too_large: "Split the statement into smaller date ranges and upload them separately.",
};

function Failed({ statement, event }: { statement: Statement; event: ProgressEvent }) {
  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card p-7">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-crit-soft text-crit"><XCircle className="h-5 w-5" /></span>
        <h1 className="mt-4 text-lg font-semibold tracking-tight text-ink">We couldn&apos;t process this file</h1>
        <p className="mt-1.5 text-sm text-ink-2">{event.message || statement.error}</p>
        {event.code && FAIL_HINTS[event.code] && <p className="mt-3 rounded-lg bg-surface-2 p-3 text-xs leading-relaxed text-ink-2">{FAIL_HINTS[event.code]}</p>}
        <Link href="/" className="mt-5 block"><Button variant="primary" className="w-full"><RotateCcw className="h-4 w-4" /> Upload another statement</Button></Link>
      </motion.div>
    </div>
  );
}
