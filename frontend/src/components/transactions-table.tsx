"use client";

import * as Popover from "@radix-ui/react-popover";
import { useVirtualizer } from "@tanstack/react-virtual";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowDownUp, Check, CircleAlert, Filter, Repeat, ScanLine, Search, UserRound, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Statement, Txn } from "@/lib/api";
import { CATEGORY_META, METHOD_LABEL } from "@/lib/categories";
import { cn, dateShort, money } from "@/lib/format";
import { useRecategorise } from "@/lib/use-txn";
import { CategoryPill } from "./category-picker";
import { Tip } from "./ui";

type Dir = "all" | "in" | "out";
type Flag = "review" | "mismatch" | "recurring" | "self" | "ocr" | "corrected";
type Sort = "date_asc" | "date_desc" | "amount_desc";

const FLAG_LABELS: Record<Flag, { label: string; icon: typeof Check }> = {
  review: { label: "Needs review", icon: AlertTriangle },
  mismatch: { label: "Doesn't add up", icon: CircleAlert },
  corrected: { label: "Auto-fixed", icon: Wand2 },
  recurring: { label: "Recurring", icon: Repeat },
  self: { label: "Self-transfer", icon: UserRound },
  ocr: { label: "From OCR", icon: ScanLine },
};

function matchFlag(t: Txn, f: Flag) {
  switch (f) {
    case "review": return t.needs_review && !t.reviewed;
    case "mismatch": return t.recon_status === "mismatch";
    case "corrected": return t.recon_status === "corrected" || t.flags.some((x) => x.endsWith("_corrected") || x === "date_inferred");
    case "recurring": return !!t.recurring_id;
    case "self": return t.self_transfer;
    case "ocr": return t.source === "ocr";
  }
}

export function ConfidenceDot({ t }: { t: Txn }) {
  const c = t.confidence;
  const tone = t.method === "user" || t.method === "learned" ? "var(--accent)" : c >= 0.85 ? "var(--good)" : c >= 0.7 ? "var(--warn)" : "var(--crit)";
  const pctTxt = t.method === "user" ? "Set by you" : `${Math.round(c * 100)}% confident`;
  return (
    <Tip content={<span><span className="font-medium text-ink">{METHOD_LABEL[t.method] ?? t.method}</span> · {pctTxt}<br />{t.explanation}</span>}>
      <span className="inline-flex h-5 items-center gap-1 text-[11px] text-muted" aria-label={pctTxt}>
        <span className="relative h-1.5 w-6 overflow-hidden rounded-full bg-surface-3">
          <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(10, c * 100)}%`, background: tone }} />
        </span>
      </span>
    </Tip>
  );
}

export function ReconIcon({ t }: { t: Txn }) {
  if (t.recon_status === "mismatch") return <Tip content={t.notes[0] ?? "Doesn't reconcile with the running balance"}><CircleAlert className="h-3.5 w-3.5 text-crit" aria-label="Does not reconcile" /></Tip>;
  if (t.recon_status === "corrected") return <Tip content={t.notes[0] ?? "Corrected from the running balance"}><Wand2 className="h-3.5 w-3.5 text-accent" aria-label="Corrected" /></Tip>;
  if (t.recon_status === "ok") return <Tip content="Matches the running balance"><Check className="h-3.5 w-3.5 text-pos" aria-label="Reconciled" /></Tip>;
  return <span className="h-3.5 w-3.5" />;
}

export function TransactionsTable({
  statement, initialCategory, initialFlag, selectedId, onOpen,
}: { statement: Statement; initialCategory: string | null; initialFlag: string | null; selectedId: string | null; onOpen: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [dir, setDir] = useState<Dir>("all");
  const [cats, setCats] = useState<Set<string>>(new Set(initialCategory ? [initialCategory] : []));
  const [flags, setFlags] = useState<Set<Flag>>(new Set(initialFlag && initialFlag in FLAG_LABELS ? [initialFlag as Flag] : []));
  const [sort, setSort] = useState<Sort>("date_asc");
  const recat = useRecategorise(statement.id);
  const parentRef = useRef<HTMLDivElement>(null);
  const hasBalance = statement.statement_type !== "credit_card";

  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    let out = statement.transactions.filter((t) => {
      if (dir === "in" && !t.credit) return false;
      if (dir === "out" && !t.debit) return false;
      if (cats.size && !cats.has(t.category)) return false;
      for (const f of flags) if (!matchFlag(t, f)) return false;
      if (term) {
        const hay = `${t.description} ${t.merchant ?? ""} ${t.counterparty ?? ""} ${t.reference ?? ""} ${t.category_name} ${t.debit ?? ""} ${t.credit ?? ""}`.toLowerCase();
        if (!hay.includes(term)) return false;
      }
      return true;
    });
    if (sort === "date_desc") out = [...out].reverse();
    if (sort === "amount_desc") out = [...out].sort((a, b) => Math.max(b.debit ?? 0, b.credit ?? 0) - Math.max(a.debit ?? 0, a.credit ?? 0));
    return out;
  }, [statement.transactions, q, dir, cats, flags, sort]);

  const totals = useMemo(() => ({
    in: rows.reduce((s, t) => s + (t.credit ?? 0), 0),
    out: rows.reduce((s, t) => s + (t.debit ?? 0), 0),
  }), [rows]);

  const virt = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => 60, overscan: 12 });

  useEffect(() => {
    if (!selectedId) return;
    const i = rows.findIndex((r) => r.id === selectedId);
    if (i >= 0) virt.scrollToIndex(i, { align: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const usedCats = useMemo(() => {
    const m = new Map<string, number>();
    statement.transactions.forEach((t) => m.set(t.category, (m.get(t.category) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [statement.transactions]);

  const filtersOn = cats.size > 0 || flags.size > 0 || dir !== "all" || q;
  const grid = hasBalance
    ? "grid-cols-[72px_minmax(0,1fr)_auto] md:grid-cols-[84px_minmax(0,1fr)_200px_40px_130px_130px_24px]"
    : "grid-cols-[72px_minmax(0,1fr)_auto] md:grid-cols-[84px_minmax(0,1fr)_200px_40px_130px_24px]";

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
        <div className="flex h-9 min-w-[220px] flex-1 items-center gap-2 rounded-[10px] border border-line bg-surface-2 px-3 focus-within:border-accent">
          <Search className="h-4 w-4 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search description, payee, amount, reference…" className="h-full flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted" />
          {q && <button onClick={() => setQ("")} aria-label="Clear search"><X className="h-3.5 w-3.5 text-muted" /></button>}
        </div>
        <div className="flex h-9 rounded-[10px] border border-line bg-surface-2 p-0.5">
          {(["all", "in", "out"] as Dir[]).map((d) => (
            <button key={d} onClick={() => setDir(d)} className={cn("relative rounded-[8px] px-3 text-[13px] transition-colors", dir === d ? "text-ink" : "text-ink-2 hover:text-ink")}>
              {dir === d && <motion.span layoutId="dir-pill" className="absolute inset-0 rounded-[8px] bg-surface shadow-[var(--shadow-sm)]" />}
              <span className="relative">{d === "all" ? "All" : d === "in" ? "Money in" : "Money out"}</span>
            </button>
          ))}
        </div>
        <Popover.Root>
          <Popover.Trigger asChild>
            <button className={cn("flex h-9 items-center gap-1.5 rounded-[10px] border px-3 text-[13px] transition-colors", cats.size ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-ink-2 hover:text-ink")}>
              <Filter className="h-3.5 w-3.5" /> Category{cats.size ? ` · ${cats.size}` : ""}
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content align="start" sideOffset={6} className="scroll-thin z-50 max-h-96 w-72 overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-pop">
              {usedCats.map(([id, n]) => {
                const M = CATEGORY_META[id] ?? CATEGORY_META.other;
                const on = cats.has(id);
                return (
                  <button key={id} onClick={() => setCats((s) => { const x = new Set(s); if (on) x.delete(id); else x.add(id); return x; })} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] text-ink hover:bg-surface-2">
                    <span className={cn("flex h-4 w-4 items-center justify-center rounded border", on ? "border-accent bg-accent text-white" : "border-line-strong")}>{on && <Check className="h-3 w-3" />}</span>
                    <M.icon className="h-3.5 w-3.5 text-ink-2" />
                    <span className="flex-1 truncate">{M.name}</span>
                    <span className="num text-[11px] text-muted">{n}</span>
                  </button>
                );
              })}
              {cats.size > 0 && <button onClick={() => setCats(new Set())} className="mt-1 w-full rounded-lg px-2 py-1.5 text-left text-xs text-accent hover:bg-surface-2">Clear categories</button>}
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
        <button onClick={() => setSort((s) => (s === "date_asc" ? "date_desc" : s === "date_desc" ? "amount_desc" : "date_asc"))} className="flex h-9 items-center gap-1.5 rounded-[10px] border border-line px-3 text-[13px] text-ink-2 hover:text-ink">
          <ArrowDownUp className="h-3.5 w-3.5" /> {sort === "date_asc" ? "Oldest first" : sort === "date_desc" ? "Newest first" : "Largest first"}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-3 py-2">
        {(Object.keys(FLAG_LABELS) as Flag[]).map((f) => {
          const n = statement.transactions.filter((t) => matchFlag(t, f)).length;
          if (!n) return null;
          const on = flags.has(f);
          const F = FLAG_LABELS[f];
          return (
            <button key={f} onClick={() => setFlags((s) => { const x = new Set(s); if (on) x.delete(f); else x.add(f); return x; })}
              className={cn("flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors", on ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-ink-2 hover:text-ink")}>
              <F.icon className="h-3 w-3" /> {F.label} <span className="num text-muted">{n}</span>
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-4 text-xs text-muted">
          <span className="num">{rows.length} of {statement.transactions.length}</span>
          <span className="num hidden sm:inline">In <span className="text-pos">{money(totals.in, { decimals: false })}</span></span>
          <span className="num hidden sm:inline">Out <span className="text-ink">{money(totals.out, { decimals: false })}</span></span>
          {filtersOn && <button onClick={() => { setQ(""); setDir("all"); setCats(new Set()); setFlags(new Set()); }} className="text-accent hover:underline">Reset</button>}
        </div>
      </div>

      <div className={cn("hidden border-b border-line bg-surface-2 px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted md:grid", grid)}>
        <span>Date</span><span>Description</span><span>Category</span><span />
        <span className="text-right">Amount</span>{hasBalance && <span className="text-right">Balance</span>}<span />
      </div>

      {rows.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-ink-2">No transactions match these filters.</p>
        </div>
      ) : (
        <div ref={parentRef} className="scroll-thin h-[min(68vh,760px)] overflow-y-auto">
          <div style={{ height: virt.getTotalSize(), position: "relative" }}>
            {virt.getVirtualItems().map((v) => {
              const t = rows[v.index];
              const amt = (t.credit ?? 0) - (t.debit ?? 0);
              const title = t.merchant || t.counterparty || t.description;
              const sel = t.id === selectedId;
              return (
                <div
                  key={t.id}
                  data-index={v.index}
                  ref={virt.measureElement}
                  onClick={() => onOpen(t.id)}
                  onKeyDown={(e) => e.key === "Enter" && onOpen(t.id)}
                  tabIndex={0}
                  role="button"
                  style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${v.start}px)` }}
                  className={cn("grid cursor-pointer items-center gap-3 border-b border-line px-4 py-2.5 transition-colors hover:bg-surface-2", grid,
                    sel && "bg-accent-soft hover:bg-accent-soft",
                    t.recon_status === "mismatch" && !sel && "bg-crit-soft/50")}
                >
                  <span className="num text-[13px] text-ink-2">
                    {dateShort(t.date)}
                    {t.flags.includes("date_inferred") && <Tip content={t.notes.find((n) => n.startsWith("OCR could not read the date")) ?? "Date inferred"}><span className="ml-1 text-warn">*</span></Tip>}
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-[13.5px] font-medium text-ink">{title}</span>
                      {t.recurring_id && <Repeat className="h-3 w-3 shrink-0 text-muted" aria-label="Recurring" />}
                      {t.self_transfer && <span className="shrink-0 rounded bg-surface-3 px-1 text-[10px] text-ink-2">self</span>}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5">
                      {t.channel && t.channel !== "OTHER" && <span className="shrink-0 rounded bg-surface-3 px-1 font-mono text-[10px] text-ink-2">{t.channel}</span>}
                      <span className="truncate text-xs text-muted" title={t.description}>{t.description}</span>
                    </span>
                    <span className="mt-1.5 block md:hidden"><CategoryPill size="sm" txn={t} onPick={(c) => recat.mutate({ txn: t, category: c })} /></span>
                  </span>
                  <span className="hidden min-w-0 md:block"><CategoryPill txn={t} onPick={(c) => recat.mutate({ txn: t, category: c })} /></span>
                  <span className="hidden md:block"><ConfidenceDot t={t} /></span>
                  <span className={cn("num text-right text-[13.5px] font-medium", amt > 0 ? "text-pos" : "text-ink")}>{money(amt, { sign: true })}</span>
                  {hasBalance && <span className="num hidden text-right text-[13px] text-ink-2 md:block">{money(t.balance)}</span>}
                  <span className="hidden justify-end md:flex"><ReconIcon t={t} /></span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

