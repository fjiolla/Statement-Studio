"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, CircleAlert, CircleDashed, EyeOff, FileText, ScanLine, Wand2 } from "lucide-react";
import type { Check, Statement } from "@/lib/api";
import { cn, date, money } from "@/lib/format";
import { Badge, ScoreRing, SectionTitle } from "./ui";

const ROLE_LABEL: Record<string, string> = {
  date: "Date", value_date: "Value date", description: "Description", ref: "Reference", debit: "Debit", credit: "Credit",
  amount: "Amount", balance: "Balance", crdr: "Cr/Dr", serial: "Serial", other: "Ignored",
};

function CheckRow({ c, i }: { c: Check; i: number }) {
  const Icon = c.status === "pass" ? CheckCircle2 : c.status === "fail" ? CircleAlert : c.status === "warn" ? AlertTriangle : CircleDashed;
  const tone = c.status === "pass" ? "text-pos" : c.status === "fail" ? "text-crit" : c.status === "warn" ? "text-warn" : "text-muted";
  const label = { pass: "Pass", fail: "Fail", warn: "Warning", skip: "Skipped" }[c.status];
  return (
    <motion.li initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }} className="flex gap-3 py-3">
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone)} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
          {c.name}
          <Badge tone={c.status === "pass" ? "pos" : c.status === "fail" ? "crit" : c.status === "warn" ? "warn" : "neutral"}>{label}</Badge>
        </p>
        <p className="num mt-0.5 text-[13px] leading-relaxed text-ink-2">{c.detail}</p>
      </div>
    </motion.li>
  );
}

export function ChecksPanel({ statement, onOpen }: { statement: Statement; onOpen: (id: string) => void }) {
  const r = statement.recon!;
  const flagged = statement.transactions.filter((t) => t.recon_status === "mismatch" || t.recon_status === "corrected" || t.flags.includes("date_inferred") || t.flags.includes("possible_duplicate"));
  const pages = statement.pages ?? [];
  const hidden = pages.reduce((s, p) => s + (p.hidden_words || 0), 0);
  const isCard = statement.statement_type === "credit_card";

  return (
    <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
      <div className="space-y-5">
        <div className="card p-5">
          <div className="flex flex-wrap items-center gap-5">
            <ScoreRing score={r.integrity_score} size={96} />
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold text-ink">Reconciliation score</h2>
              <p className="mt-1 text-sm text-ink-2">
                {isCard ? "Previous balance + charges − payments = total due" : "Previous balance ± amount = balance, for every row"}
              </p>
              {!isCard && (
                <div className="num mt-3 flex flex-wrap gap-2 text-xs">
                  <Badge tone="pos">{r.ok_rows} reconcile</Badge>
                  {r.corrected_rows > 0 && <Badge tone="accent">{r.corrected_rows} corrected</Badge>}
                  {r.mismatched_rows > 0 && <Badge tone="crit">{r.mismatched_rows} don&apos;t add up</Badge>}
                  <Badge>Order: {r.order === "descending" ? "newest first (re-sorted)" : "oldest first"}</Badge>
                </div>
              )}
            </div>
          </div>
          <ul className="mt-4 divide-y divide-[var(--border)] border-t border-line">
            {r.checks.map((c, i) => <CheckRow key={c.name} c={c} i={i} />)}
          </ul>
        </div>

        <div className="card p-5">
          <SectionTitle title="Rows to look at" />
          {flagged.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">No inconsistent, corrected or inferred rows.</p>
          ) : (
            <ul className="divide-y divide-[var(--border)]">
              {flagged.map((t) => (
                <li key={t.id}>
                  <button onClick={() => onOpen(t.id)} className="flex w-full items-start gap-3 py-3 text-left hover:opacity-80">
                    {t.recon_status === "mismatch" ? <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-crit" /> : <Wand2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" />}
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-[13px] font-medium text-ink">{date(t.date)} · {t.merchant || t.counterparty || t.description}</span>
                        <span className="num shrink-0 text-[13px] text-ink">{money((t.credit ?? 0) - (t.debit ?? 0), { sign: true })}</span>
                      </span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-ink-2">{t.notes.join(" ")}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="space-y-5">
        {hidden > 0 && (
          <div className="rounded-xl bg-crit-soft p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-ink"><EyeOff className="h-4 w-4 text-crit" /> Possible tampering</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">
              {hidden} text fragment{hidden > 1 ? "s are" : " is"} hidden under shapes. Only visible text was read.
            </p>
          </div>
        )}

        <div className="card p-5">
          <SectionTitle title="How it was read" hint={`${statement.page_count} page${statement.page_count === 1 ? "" : "s"} · ${statement.timings?.total?.toFixed(1)}s total`} />
          <ul className="space-y-1.5">
            {pages.map((p) => (
              <li key={p.index} className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2 text-[13px]">
                {p.kind === "scanned" ? <ScanLine className="h-4 w-4 text-accent" /> : <FileText className="h-4 w-4 text-ink-2" />}
                <span className="w-14 text-ink">Page {p.index + 1}</span>
                <span className="flex-1 text-ink-2">
                  {p.kind === "scanned" ? `Scanned → ${p.ocr_engine === "tesseract" ? "Tesseract" : "RapidOCR"}` : p.kind === "hybrid" ? "Scan with text layer" : p.kind === "empty" ? "Blank" : "Text layer"}
                </span>
                {p.ocr_confidence != null && <span className="num text-xs text-muted">{Math.round(p.ocr_confidence * 100)}% · {p.ocr_seconds}s</span>}
                {p.hidden_words > 0 && <Badge tone="crit">{p.hidden_words} hidden</Badge>}
              </li>
            ))}
          </ul>
        </div>

        {statement.columns && statement.columns.length > 0 && (
          <div className="card p-5">
            <SectionTitle title="Columns detected" />
            <ul className="space-y-1.5">
              {statement.columns.map((c, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="truncate font-mono text-xs text-ink-2">“{c.label}”</span>
                  <span className={cn("shrink-0", c.role === "other" ? "text-muted" : "text-ink")}>→ {ROLE_LABEL[c.role] ?? c.role}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
