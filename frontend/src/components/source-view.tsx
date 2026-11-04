"use client";

import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Statement } from "@/lib/api";
import { catMeta } from "@/lib/categories";
import { cn, dateShort, money } from "@/lib/format";
import type { Highlight } from "./pdf";
import { Button, Skeleton } from "./ui";

const PdfPage = dynamic(() => import("./pdf").then((m) => m.PdfPage), { ssr: false, loading: () => <Skeleton className="h-[900px] w-full" /> });

/** The original PDF with every extracted row outlined; click a row on the page or in the list to inspect it. */
export function SourceView({ statement, onOpen, selectedId }: { statement: Statement; onOpen: (id: string) => void; selectedId: string | null }) {
  const pages = statement.page_count ?? 1;
  const selected = statement.transactions.find((t) => t.id === selectedId);
  const [page, setPage] = useState(selected?.bboxes?.[0]?.page ?? 0);
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.min(900, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    if (selected?.bboxes?.[0]) setPage(selected.bboxes[0].page);
  }, [selected]);

  const onPage = useMemo(() => statement.transactions.filter((t) => t.bboxes?.some((b) => b.page === page)), [statement.transactions, page]);
  const highlights: Highlight[] = onPage.flatMap((t) =>
    t.bboxes.filter((b) => b.page === page).map((b, i) => ({
      id: `${t.id}#${i}`,
      box: b,
      tone: t.id === selectedId ? "selected" : t.recon_status === "mismatch" ? "mismatch" : t.needs_review && !t.reviewed ? "review" : "ok",
      label: `${t.merchant || t.counterparty || t.description} · ${money((t.credit ?? 0) - (t.debit ?? 0), { sign: true })}`,
    })),
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="card p-4">
        <div className="mb-3 flex items-center gap-2">
          <Button size="icon" variant="ghost" disabled={page <= 0} onClick={() => setPage((p) => p - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></Button>
          <span className="num text-sm text-ink">Page {page + 1} <span className="text-muted">of {pages}</span></span>
          <Button size="icon" variant="ghost" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4" /></Button>
          <div className="ml-auto flex items-center gap-3 text-[11px] text-muted">
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm ring-1 ring-[var(--crit)]" style={{ background: "var(--crit-soft)" }} /> doesn&apos;t add up</span>
            <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "var(--warn-soft)" }} /> to review</span>
            <a href={api.pdfUrl(statement.id)} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-ink-2 hover:text-ink"><ExternalLink className="h-3 w-3" /> Open</a>
          </div>
        </div>
        <div ref={wrap} className="flex justify-center rounded-xl bg-surface-2 p-3">
          <PdfPage key={page} url={api.pdfUrl(statement.id)} pageIndex={page} width={Math.max(320, width - 24)} highlights={highlights} onPick={(id) => onOpen(id.split("#")[0])} />
        </div>
      </div>
      <div className="card flex max-h-[calc(100vh-200px)] flex-col overflow-hidden lg:sticky lg:top-32">
        <div className="border-b border-line px-4 py-3">
          <h3 className="text-sm font-semibold text-ink">On this page</h3>
          <p className="text-xs text-muted">{onPage.length} transaction{onPage.length === 1 ? "" : "s"} extracted</p>
        </div>
        <ul className="scroll-thin flex-1 overflow-y-auto p-1.5">
          {onPage.length === 0 && <li className="px-3 py-8 text-center text-sm text-muted">No transactions on this page (summary, terms, or blank).</li>}
          {onPage.map((t) => {
            const Icon = catMeta(t.category).icon;
            const amt = (t.credit ?? 0) - (t.debit ?? 0);
            return (
              <li key={t.id}>
                <button onClick={() => onOpen(t.id)} className={cn("flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-2", t.id === selectedId && "bg-accent-soft")}>
                  <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
                  <span className="w-12 shrink-0 text-xs text-muted">{dateShort(t.date)}</span>
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{t.merchant || t.counterparty || t.description}</span>
                  <span className={cn("num text-[13px]", amt > 0 ? "text-pos" : "text-ink")}>{money(amt, { sign: true, decimals: false })}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
