"use client";

import * as Popover from "@radix-ui/react-popover";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, CircleAlert, PartyPopper, SkipForward } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { api, type Statement, type Txn } from "@/lib/api";
import { METHOD_LABEL, catMeta } from "@/lib/categories";
import { cn, date, money } from "@/lib/format";
import { useAcceptSuggestion, useMarkReviewed, useRecategorise } from "@/lib/use-txn";
import { CategoryCommand } from "./category-picker";
import { Badge, Button, Kbd, Skeleton } from "./ui";

const PdfSnippet = dynamic(() => import("./pdf").then((m) => m.PdfSnippet), { ssr: false, loading: () => <Skeleton className="h-20 w-full" /> });

export function ReviewQueue({ statement, onOpen }: { statement: Statement; onOpen: (id: string) => void }) {
  const queue = useMemo(() => statement.transactions.filter((t) => t.needs_review && !t.reviewed), [statement.transactions]);
  const total = useMemo(() => statement.transactions.filter((t) => t.needs_review || (t.reviewed && t.method === "user")).length, [statement.transactions]);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const items = queue.filter((t) => !skipped.has(t.id)).concat(queue.filter((t) => skipped.has(t.id)));
  const current = items[0];
  const done = total - queue.length;

  if (!current) {
    return (
      <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="card mx-auto flex max-w-xl flex-col items-center px-6 py-16 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-pos-soft text-pos"><PartyPopper className="h-6 w-6" /></span>
        <h2 className="mt-4 text-lg font-semibold tracking-tight text-ink">Nothing left to review</h2>
        <p className="mt-1.5 max-w-sm text-sm text-ink-2">
          Every transaction is either confidently categorised or confirmed by you. Your corrections are saved as rules for future statements.
        </p>
      </motion.div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center gap-4">
        <div className="flex-1">
          <div className="flex justify-between text-xs text-ink-2">
            <span>{queue.length} left to review</span>
            <span className="num">{done}/{total} done</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
            <motion.div className="h-full rounded-full bg-accent" animate={{ width: `${total ? (done / total) * 100 : 0}%` }} />
          </div>
        </div>
        <span className="hidden items-center gap-1.5 text-[11px] text-muted md:flex">
          <Kbd>1</Kbd>–<Kbd>3</Kbd> pick <Kbd>↵</Kbd> keep <Kbd>/</Kbd> other <Kbd>S</Kbd> skip
        </span>
      </div>
      <AnimatePresence mode="popLayout">
        <ReviewCard key={current.id} statement={statement} txn={current} onSkip={() => setSkipped((s) => new Set(s).add(current.id))} onOpen={onOpen} />
      </AnimatePresence>
      {items.length > 1 && (
        <div className="mt-6">
          <p className="mb-2 text-xs text-muted">Up next</p>
          <ul className="space-y-1.5">
            {items.slice(1, 6).map((t) => (
              <li key={t.id} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5 opacity-80">
                <span className="w-20 text-xs text-muted">{date(t.date)}</span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{t.merchant || t.counterparty || t.description}</span>
                {t.recon_status === "mismatch" && <CircleAlert className="h-3.5 w-3.5 text-crit" />}
                <span className="num text-[13px] text-ink-2">{money((t.credit ?? 0) - (t.debit ?? 0), { sign: true })}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ReviewCard({ statement, txn, onSkip, onOpen }: { statement: Statement; txn: Txn; onSkip: () => void; onOpen: (id: string) => void }) {
  const recat = useRecategorise(statement.id);
  const keep = useMarkReviewed(statement.id);
  const accept = useAcceptSuggestion(statement.id);
  const [pickerOpen, setPickerOpen] = useState(false);
  const amt = (txn.credit ?? 0) - (txn.debit ?? 0);
  const options = [txn.category, ...(txn.alternatives ?? []).map((a) => a.category).filter((c) => c !== txn.category)].slice(0, 3);
  const choose = (cat: string) => (cat === txn.category ? keep.mutate(txn) : recat.mutate({ txn, category: cat }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (pickerOpen || (e.target as HTMLElement)?.closest("input,textarea,[cmdk-root]")) return;
      if (["1", "2", "3"].includes(e.key) && options[+e.key - 1]) { e.preventDefault(); choose(options[+e.key - 1]); }
      else if (e.key === "Enter") { e.preventDefault(); choose(txn.category); }
      else if (e.key.toLowerCase() === "s") { e.preventDefault(); onSkip(); }
      else if (e.key === "/") { e.preventDefault(); setPickerOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: -40, transition: { duration: 0.18 } }}
      className="card overflow-hidden"
    >
      <div className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-muted">{date(txn.date)} · {txn.channel && txn.channel !== "OTHER" ? txn.channel : "Statement entry"}</p>
            <h2 className="mt-1 truncate text-lg font-semibold tracking-tight text-ink">{txn.merchant || txn.counterparty || txn.description}</h2>
            <p className="mt-1 break-words font-mono text-[12px] text-ink-2">{txn.description}</p>
          </div>
          <p className={cn("num shrink-0 text-2xl font-semibold tracking-tight", amt > 0 ? "text-pos" : "text-ink")}>{money(amt, { sign: true })}</p>
        </div>

        {txn.bboxes?.[0] && (
          <div className="scroll-thin mt-4 overflow-x-auto"><PdfSnippet url={api.pdfUrl(statement.id)} box={txn.bboxes[0]} width={660} pad={8} /></div>
        )}

        <div className="mt-4 rounded-xl bg-surface-2 p-3.5 text-[13px] text-ink-2">
          <span className="font-medium text-ink">Why it&apos;s here: </span>
          {txn.recon_status === "mismatch"
            ? txn.notes[0] ?? "This row doesn't reconcile with the running balance."
            : <>{METHOD_LABEL[txn.method] ?? txn.method} was only {Math.round(txn.confidence * 100)}% sure. {txn.explanation}</>}
        </div>
        {txn.suggestion && (
          <div className="mt-3 flex items-center gap-3 rounded-xl border border-line p-3.5">
            <p className="flex-1 text-[13px] text-ink">Suggested fix: set {txn.suggestion.field} to <span className="num font-semibold">{money(txn.suggestion.value)}</span>. <span className="text-muted">{txn.suggestion.reason}</span></p>
            <Button size="sm" onClick={() => accept.mutate(txn)} loading={accept.isPending}>Apply</Button>
          </div>
        )}
      </div>
      <div className="border-t border-line bg-surface-2/60 p-4">
        <p className="mb-2.5 text-xs text-muted">Which category fits?</p>
        <div className="flex flex-wrap gap-2">
          {options.map((c, i) => {
            const M = catMeta(c);
            const alt = txn.alternatives?.find((a) => a.category === c);
            return (
              <button
                key={c}
                onClick={() => choose(c)}
                className={cn("group flex h-10 items-center gap-2 rounded-xl border px-3 text-sm transition-all hover:-translate-y-px hover:shadow-card",
                  c === txn.category ? "border-accent bg-accent-soft text-ink" : "border-line bg-surface text-ink")}
              >
                <Kbd>{i + 1}</Kbd>
                <M.icon className="h-4 w-4 text-ink-2" />
                {M.name}
                {alt && <span className="num text-xs text-muted">{Math.round(alt.score * 100)}%</span>}
                {c === txn.category && <Badge tone="accent">current</Badge>}
              </button>
            );
          })}
          <Popover.Root open={pickerOpen} onOpenChange={setPickerOpen}>
            <Popover.Trigger asChild>
              <button className="flex h-10 items-center gap-2 rounded-xl border border-dashed border-line-strong px-3 text-sm text-ink-2 hover:text-ink"><Kbd>/</Kbd> Something else…</button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content sideOffset={6} className="z-[70] w-72 overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
                <CategoryCommand txn={txn} onPick={(c) => { setPickerOpen(false); choose(c); }} />
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" size="sm" className="h-10" onClick={() => onOpen(txn.id)}>Details</Button>
            <Button variant="ghost" size="sm" className="h-10" onClick={onSkip}><SkipForward className="h-4 w-4" /> Skip</Button>
            <Button size="sm" className="h-10" onClick={() => choose(txn.category)}><CheckCircle2 className="h-4 w-4" /> Looks right</Button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
