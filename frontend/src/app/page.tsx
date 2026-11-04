"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowUpRight, CreditCard, FileText, KeyRound, Layers, Loader2, ScanLine, ShieldAlert, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge, Tip } from "@/components/ui";
import { UploadZone } from "@/components/upload-zone";
import { api, type StatementSummary } from "@/lib/api";
import { dateShort, maskAccount } from "@/lib/format";

export default function Home() {
  return (
    <div className="mx-auto max-w-[1100px] px-4 pb-24 pt-12 sm:px-6 sm:pt-16">
      <section className="grid items-start gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-14">
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <h1 className="text-[34px] font-semibold leading-[1.1] tracking-[-0.025em] text-ink sm:text-[40px]">
            Bank statements to clean spreadsheets.
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-2">
            Digital or scanned PDFs from Indian banks and cards. Every balance is checked and every transaction categorised.
          </p>
          <Samples />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 }}>
          <UploadZone />
        </motion.div>
      </section>
      <Recent />
    </div>
  );
}

const SAMPLE_ICON: Record<string, typeof FileText> = {
  text: FileText, scanned: ScanLine, protected: KeyRound, tampered: ShieldAlert, card: CreditCard,
};

function Samples() {
  const router = useRouter();
  const qc = useQueryClient();
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });
  const load = useMutation({
    mutationFn: api.loadSample,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      router.push(`/statements/${r.id}`);
    },
    onError: (e: Error) => toast.error("Couldn't load sample", { description: e.message }),
  });
  if (!samples.data?.length) return null;
  return (
    <div className="mt-10">
      <p className="mb-2 text-xs font-medium text-muted">Try a sample</p>
      <ul className="divide-y divide-[var(--border)] border-y border-line">
        {samples.data.map((s) => {
          const Icon = SAMPLE_ICON[s.kind] ?? FileText;
          const busy = load.isPending && load.variables === s.file;
          return (
            <li key={s.file}>
              <button
                onClick={() => load.mutate(s.file)}
                disabled={load.isPending}
                className="group flex w-full items-center gap-3 py-2.5 text-left disabled:opacity-60"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin text-muted" /> : <Icon className="h-4 w-4 text-muted" />}
                <span className="flex-1 truncate text-sm text-ink group-hover:text-accent-ink">{s.title}</span>
                <span className={s.kind === "tampered" ? "text-xs text-crit" : "text-xs text-muted"}>{s.tag}</span>
                <ArrowUpRight className="h-3.5 w-3.5 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Status({ s }: { s: StatementSummary }) {
  if (s.status === "done") {
    const v = s.integrity_score;
    if (v === null) return <span className="text-xs text-muted">Not verifiable</span>;
    const tone = v >= 99 ? "text-pos" : v >= 90 ? "text-warn" : "text-crit";
    return <span className={`num text-xs ${tone}`}>{v >= 99.95 ? "100" : v.toFixed(1)}% reconciled</span>;
  }
  if (s.status === "failed") return <span className="text-xs text-crit">Failed</span>;
  if (s.status === "needs_password") return <span className="text-xs text-warn">Needs password</span>;
  return <span className="flex items-center gap-1 text-xs text-muted"><Loader2 className="h-3 w-3 animate-spin" /> Processing</span>;
}

function Recent() {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["statements"],
    queryFn: api.list,
    refetchInterval: (q) => ((q.state.data ?? []).some((s) => s.status === "queued" || s.status === "processing") ? 2000 : false),
  });
  const del = useMutation({
    mutationFn: api.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      toast("Statement deleted");
    },
  });
  if (list.isError) {
    return (
      <div className="mt-14 flex items-center gap-2 text-sm text-ink-2">
        <AlertTriangle className="h-4 w-4 text-warn" /> Can&apos;t reach the API. Start the backend and refresh.
      </div>
    );
  }
  const rows = list.data ?? [];
  if (!rows.length) return null;
  const ids = rows.filter((r) => r.status === "done").map((r) => r.id);
  return (
    <section className="mt-16">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">Your statements</h2>
        <div className="flex items-center gap-4">
          {ids.length > 1 && (
            <a href={api.exportUrl(ids, "xlsx")} className="flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink">
              <Layers className="h-3.5 w-3.5" /> Export all to one workbook
            </a>
          )}
          <span className="text-xs text-muted">Deleted after 24 h</span>
        </div>
      </div>
      <div className="card overflow-hidden">
        <AnimatePresence initial={false}>
          {rows.map((s) => (
            <motion.div
              key={s.id}
              layout
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, height: 0 }}
              className="group flex items-center gap-3 border-b border-line pr-2 last:border-b-0 hover:bg-surface-2"
            >
              <Link href={`/statements/${s.id}`} className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-4">
                <span className="text-muted">
                  {s.statement_type === "credit_card" ? <CreditCard className="h-4 w-4" /> : s.document_type === "scanned" ? <ScanLine className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm text-ink">{s.bank_name || s.filename}</span>
                    {s.account_number && <span className="num shrink-0 text-xs text-muted">{maskAccount(s.account_number)}</span>}
                    {s.overlaps_with && s.overlaps_with.length > 0 && (
                      <Tip content="Overlaps another statement for this account. Combined exports remove duplicate rows.">
                        <span><Badge tone="warn">Overlap</Badge></span>
                      </Tip>
                    )}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-muted">
                    {s.status === "done"
                      ? `${dateShort(s.period_from)} – ${dateShort(s.period_to)} · ${s.transactions} rows${s.review_count ? ` · ${s.review_count} to review` : ""}`
                      : s.status === "failed" ? s.error : s.filename}
                  </span>
                </span>
                <span className="hidden w-32 text-right sm:block"><Status s={s} /></span>
              </Link>
              <button
                onClick={() => del.mutate(s.id)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted opacity-0 transition-opacity hover:bg-crit-soft hover:text-crit focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                aria-label={`Delete ${s.filename}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </section>
  );
}
