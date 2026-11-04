"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, ChevronUp, CircleAlert, Info, Repeat, ScanLine, Sparkles, Wand2, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api, type Statement, type Txn } from "@/lib/api";
import { METHOD_LABEL, catMeta } from "@/lib/categories";
import { cn, date, money } from "@/lib/format";
import { useAcceptSuggestion, useNote, useRecategorise } from "@/lib/use-txn";
import { CategoryPill } from "./category-picker";
import { Badge, Button, Kbd, Skeleton } from "./ui";

const PdfSnippet = dynamic(() => import("./pdf").then((m) => m.PdfSnippet), { ssr: false, loading: () => <Skeleton className="h-24 w-full" /> });

export function TxnDrawer({ statement, txn, onClose }: { statement: Statement; txn: Txn | null; onClose: () => void }) {
  return (
    <Dialog.Root open={!!txn} onOpenChange={(o) => !o && onClose()}>
      <AnimatePresence>
        {txn && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[1px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount aria-describedby={undefined}>
              <motion.aside
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ type: "spring", stiffness: 420, damping: 40 }}
                className="scroll-thin fixed inset-y-0 right-0 z-50 flex w-full max-w-[600px] flex-col overflow-y-auto border-l border-line bg-surface shadow-pop"
              >
                <DrawerBody statement={statement} txn={txn} onClose={onClose} />
              </motion.aside>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}

function DrawerBody({ statement, txn, onClose }: { statement: Statement; txn: Txn; onClose: () => void }) {
  const recat = useRecategorise(statement.id);
  const accept = useAcceptSuggestion(statement.id);
  const noteMut = useNote(statement.id);
  const [note, setNote] = useState(txn.user_note ?? "");
  useEffect(() => setNote(txn.user_note ?? ""), [txn.id, txn.user_note]);

  const list = statement.transactions;
  const i = list.findIndex((t) => t.id === txn.id);
  const go = (d: number) => {
    const n = list[i + d];
    if (n) {
      const p = new URLSearchParams(window.location.search);
      p.set("txn", n.id);
      // Next.js syncs native history updates with useSearchParams
      window.history.replaceState(null, "", `?${p.toString()}`);
    }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "TEXTAREA" || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); go(1); }
      if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); go(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const amt = (txn.credit ?? 0) - (txn.debit ?? 0);
  const meta = catMeta(txn.category);
  const recurring = statement.recurring?.find((g) => g.id === txn.recurring_id);
  const conf = txn.confidence;
  const details: [string, React.ReactNode][] = [
    ["Description", <span key="d" className="break-words font-mono text-[12px] leading-relaxed">{txn.description}</span>],
    ["Reference", txn.reference || "—"],
    ["Value date", date(txn.value_date)],
    ["Channel", txn.channel && txn.channel !== "OTHER" ? txn.channel : "—"],
    ["Counterparty", txn.counterparty || "—"],
    ["UPI ID", txn.vpa || "—"],
    ["Balance after", money(txn.balance)],
    ["Debit / credit from", { column: "Separate debit & credit columns", marker: "Dr/Cr marker", balance: "Running balance", default: "Default (card spend)" }[txn.direction_source] ?? txn.direction_source],
    ["Read via", txn.source === "ocr" ? `OCR${txn.ocr_confidence ? ` · ${Math.round(txn.ocr_confidence * 100)}% confidence` : ""}` : "PDF text layer"],
    ["Source page", `Page ${(txn.page ?? 0) + 1}`],
  ];

  return (
    <>
      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-surface/90 px-5 py-3 backdrop-blur">
        <Dialog.Title className="flex-1 text-sm font-medium text-ink-2">Transaction <span className="num text-muted">{i + 1} of {list.length}</span></Dialog.Title>
        <span className="hidden items-center gap-1 text-[11px] text-muted sm:flex"><Kbd>↑</Kbd><Kbd>↓</Kbd> to move</span>
        <Button size="icon" variant="ghost" onClick={() => go(-1)} disabled={i <= 0} aria-label="Previous"><ChevronUp className="h-4 w-4" /></Button>
        <Button size="icon" variant="ghost" onClick={() => go(1)} disabled={i >= list.length - 1} aria-label="Next"><ChevronDown className="h-4 w-4" /></Button>
        <Dialog.Close asChild><Button size="icon" variant="ghost" aria-label="Close"><X className="h-4 w-4" /></Button></Dialog.Close>
      </div>

      <motion.div key={txn.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className="space-y-6 p-5 sm:p-6">
        <div>
          <p className="text-xs text-muted">{date(txn.date)}{txn.flags.includes("date_inferred") && " · inferred"}</p>
          <h2 className="mt-1 text-lg font-semibold leading-snug tracking-tight text-ink">{txn.merchant || txn.counterparty || txn.description}</h2>
          <p className={cn("num mt-2 text-[32px] font-semibold tracking-tight", amt > 0 ? "text-pos" : "text-ink")}>{money(amt, { sign: true })}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <CategoryPill txn={txn} onPick={(c) => recat.mutate({ txn, category: c })} />
            {txn.self_transfer && <Badge>Own account</Badge>}
            {recurring && <Badge tone="accent"><Repeat className="h-3 w-3" /> {recurring.cadence} · {recurring.count}×</Badge>}
            {txn.source === "ocr" && <Badge><ScanLine className="h-3 w-3" /> OCR</Badge>}
          </div>
        </div>

        <section className="rounded-xl border border-line bg-surface-2 p-4">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Sparkles className="h-3.5 w-3.5" /> Why {meta.name}</h3>
            <Badge tone={txn.method === "user" || txn.method === "learned" ? "accent" : conf >= 0.85 ? "pos" : conf >= 0.7 ? "warn" : "crit"}>
              {METHOD_LABEL[txn.method] ?? txn.method}{txn.method !== "user" && ` · ${Math.round(conf * 100)}%`}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-ink">{txn.explanation}</p>
          {txn.method !== "user" && (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <motion.div className="h-full rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${conf * 100}%` }} transition={{ duration: 0.6 }} />
            </div>
          )}
          {txn.alternatives?.filter((a) => a.category !== txn.category && a.score >= 0.05).length > 0 && txn.method !== "user" && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted">Or perhaps</span>
              {txn.alternatives.filter((a) => a.category !== txn.category && a.score >= 0.05).slice(0, 3).map((a) => {
                const M = catMeta(a.category);
                return (
                  <button key={a.category} onClick={() => recat.mutate({ txn, category: a.category })} className="flex h-7 items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 text-xs text-ink-2 transition-colors hover:border-accent hover:text-ink">
                    <M.icon className="h-3 w-3" /> {M.name} <span className="num text-muted">{Math.round(a.score * 100)}%</span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {txn.bboxes?.[0] && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">On the statement · page {txn.bboxes[0].page + 1}</h3>
            <div className="scroll-thin overflow-x-auto">
              <PdfSnippet url={api.pdfUrl(statement.id)} box={txn.bboxes[0]} width={548} />
            </div>
          </section>
        )}

        <section className={cn("rounded-xl border p-4",
          txn.recon_status === "mismatch" ? "border-[color-mix(in_oklab,var(--crit)_40%,transparent)] bg-crit-soft" :
          txn.recon_status === "corrected" ? "border-line bg-accent-soft" : "border-line")}>
          <h3 className="flex items-center gap-1.5 text-sm font-medium text-ink">
            {txn.recon_status === "ok" && <><Check className="h-4 w-4 text-pos" /> Matches the running balance</>}
            {txn.recon_status === "mismatch" && <><CircleAlert className="h-4 w-4 text-crit" /> Doesn&apos;t add up</>}
            {txn.recon_status === "corrected" && <><Wand2 className="h-4 w-4 text-accent" /> Corrected</>}
            {txn.recon_status === "unverified" && <><Info className="h-4 w-4 text-muted" /> Not verifiable{statement.statement_type === "credit_card" ? " (card statements have no running balance)" : " (first row, or no balance)"}</>}
          </h3>
          {txn.notes?.length > 0 && <ul className="mt-2 space-y-1 text-[13px] text-ink-2">{txn.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          {txn.suggestion && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg bg-surface p-3">
              <p className="flex-1 text-[13px] text-ink">
                Set {txn.suggestion.field} to <span className="num font-semibold">{money(txn.suggestion.value)}</span>?
                <span className="block text-xs text-muted">{txn.suggestion.reason} Check the snippet above first.</span>
              </p>
              <Button size="sm" variant="primary" loading={accept.isPending} onClick={() => accept.mutate(txn)}>Apply fix</Button>
            </div>
          )}
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Details</h3>
          <dl className="divide-y divide-[var(--border)] rounded-xl border border-line">
            {details.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[130px_minmax(0,1fr)] gap-3 px-3.5 py-2.5 text-[13px]">
                <dt className="text-muted">{k}</dt>
                <dd className="min-w-0 break-words text-ink">{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <label htmlFor="note" className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted">Your note</label>
          <textarea
            id="note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (txn.user_note ?? "") && noteMut.mutate({ txn, note })}
            placeholder="Add context — it's included in the export."
            rows={2}
            className="w-full resize-none rounded-xl border border-line bg-surface-2 p-3 text-sm text-ink outline-none placeholder:text-muted focus:border-accent"
          />
        </section>
      </motion.div>
    </>
  );
}
