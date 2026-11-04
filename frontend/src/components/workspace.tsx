"use client";

import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ChevronDown, CreditCard, Download, FileSpreadsheet, FileText, Landmark, MoreHorizontal, Sheet, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { toast } from "sonner";
import { api, type Statement } from "@/lib/api";
import { cn, date, maskAccount } from "@/lib/format";
import { ChecksPanel } from "./checks-panel";
import { Overview } from "./overview";
import { ReviewQueue } from "./review-queue";
import { SourceView } from "./source-view";
import { TransactionsTable } from "./transactions-table";
import { TxnDrawer } from "./txn-drawer";
import { Badge, Button } from "./ui";

const TABS = ["overview", "transactions", "review", "checks", "source"] as const;
type Tab = (typeof TABS)[number];

export function Workspace({ statement }: { statement: Statement }) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const tab = (TABS.includes(params.get("tab") as Tab) ? params.get("tab") : "overview") as Tab;
  const txnId = params.get("txn");

  const setParams = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(next)) (v === null ? p.delete(k) : p.set(k, v));
      router.replace(`${path}?${p.toString()}`, { scroll: false });
    },
    [params, path, router],
  );

  const reviewCount = useMemo(() => statement.transactions.filter((t) => t.needs_review && !t.reviewed).length, [statement.transactions]);
  const issues = statement.recon?.checks.filter((c) => c.status === "fail" || c.status === "warn").length ?? 0;
  const meta = statement.meta ?? {};
  const isCard = statement.statement_type === "credit_card";
  const selected = txnId ? statement.transactions.find((t) => t.id === txnId) ?? null : null;

  const labels: Record<Tab, React.ReactNode> = {
    overview: "Overview",
    transactions: <>Transactions <span className="num ml-1 text-muted">{statement.transactions.length}</span></>,
    review: <>Review {reviewCount > 0 && <span className="num ml-1 rounded-full bg-warn-soft px-1.5 text-[11px] text-warn">{reviewCount}</span>}</>,
    checks: <>Checks {issues > 0 && <span className="num ml-1 rounded-full bg-crit-soft px-1.5 text-[11px] text-crit">{issues}</span>}</>,
    source: "Source PDF",
  };

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 sm:px-6">
      <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-start gap-4 pb-2 pt-6">
        <Link href="/" className="mt-1 flex h-9 w-9 items-center justify-center rounded-[10px] text-ink-2 hover:bg-surface-2 hover:text-ink" aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="hidden h-11 w-11 items-center justify-center rounded-lg border border-line bg-surface text-ink-2 sm:flex">
          {isCard ? <CreditCard className="h-5 w-5" /> : <Landmark className="h-5 w-5" />}
        </div>
        <div className="min-w-0 flex-1 basis-[calc(100%-56px)] sm:basis-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-semibold tracking-tight text-ink">{(meta.bank_name as string) || statement.filename}</h1>
            {statement.is_sample && <Badge>Sample</Badge>}
          </div>
          <p className="mt-1 text-sm text-ink-2 sm:truncate">
            {(meta.account_holder as string) || "Account holder not found"}
            <span className="mx-2 text-muted">·</span>
            {isCard ? "Credit card" : "Bank account"}
            <span className="mx-2 text-muted">·</span>
            {statement.document_type === "mixed" ? "Mixed pages" : statement.document_type === "scanned" ? "Scanned" : "Digital PDF"}
            <span className="mx-2 text-muted">·</span>
            <span className="num">{maskAccount((meta.account_number || meta.card_number) as string)}</span>
            <span className="mx-2 text-muted">·</span>
            {date(meta.period_from as string)} – {date(meta.period_to as string)}
          </p>
        </div>
        <div className="flex w-full items-center gap-2 sm:w-auto [&>*:first-child]:flex-1 sm:[&>*:first-child]:flex-none">
          <ExportMenu statement={statement} reviewCount={reviewCount} />
          <MoreMenu statement={statement} />
        </div>
      </motion.div>

      <div className="sticky top-14 z-30 -mx-4 mb-6 border-b border-line bg-bg px-4 sm:-mx-6 sm:px-6">
        <div role="tablist" className="scroll-thin flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setParams({ tab: t === "overview" ? null : t })}
              className={cn("relative whitespace-nowrap px-3 py-3 text-sm transition-colors", tab === t ? "text-ink" : "text-ink-2 hover:text-ink")}
            >
              {labels[t]}
              {tab === t && <motion.span layoutId="tab-underline" className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-ink" />}
            </button>
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}>
          {tab === "overview" && <Overview statement={statement} onFilter={(f) => setParams({ tab: "transactions", ...f })} onOpenTxn={(id) => setParams({ txn: id })} />}
          {tab === "transactions" && (
            <TransactionsTable statement={statement} initialCategory={params.get("category")} initialFlag={params.get("flag")} selectedId={txnId} onOpen={(id) => setParams({ txn: id })} />
          )}
          {tab === "review" && <ReviewQueue statement={statement} onOpen={(id) => setParams({ txn: id })} />}
          {tab === "checks" && <ChecksPanel statement={statement} onOpen={(id) => setParams({ txn: id })} />}
          {tab === "source" && <SourceView statement={statement} onOpen={(id) => setParams({ txn: id })} selectedId={txnId} />}
        </motion.div>
      </AnimatePresence>

      <TxnDrawer statement={statement} txn={selected} onClose={() => setParams({ txn: null })} />
    </div>
  );
}

function ExportMenu({ statement, reviewCount }: { statement: Statement; reviewCount: number }) {
  const item = "flex cursor-pointer items-start gap-3 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2";
  const download = (href: string, label: string) => {
    const a = document.createElement("a");
    a.href = href;
    a.click();
    toast(`Downloading ${label}`);
  };
  return (
    <Dropdown.Root>
      <Dropdown.Trigger asChild>
        <Button variant="primary"><Download className="h-4 w-4" /> Export <ChevronDown className="h-3.5 w-3.5 opacity-80" /></Button>
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={6} className="z-50 w-60 rounded-lg border border-line bg-surface p-1 shadow-pop">
          <Dropdown.Item className={item} onSelect={() => download(api.exportUrl([statement.id], "xlsx"), "Excel workbook")}>
            <FileSpreadsheet className="mt-0.5 h-4 w-4 text-pos" />
            <span><span className="block font-medium text-ink">Excel (.xlsx)</span><span className="text-xs text-ink-2">All sheets, with charts</span></span>
          </Dropdown.Item>
          <Dropdown.Item className={item} onSelect={() => download(api.exportUrl([statement.id], "csv"), "CSV")}>
            <Sheet className="mt-0.5 h-4 w-4 text-ink-2" />
            <span><span className="block font-medium text-ink">CSV (.csv)</span><span className="text-xs text-ink-2">Transactions only</span></span>
          </Dropdown.Item>
          {reviewCount > 0 && (
            <Dropdown.Item className={item} onSelect={() => download(api.exportUrl([statement.id], "xlsx", true), "review rows")}>
              <FileSpreadsheet className="mt-0.5 h-4 w-4 text-warn" />
              <span><span className="block font-medium text-ink">Rows to review</span><span className="text-xs text-ink-2">{reviewCount} rows</span></span>
            </Dropdown.Item>
          )}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

function MoreMenu({ statement }: { statement: Statement }) {
  const router = useRouter();
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.remove(statement.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      toast("Statement deleted", { description: "The PDF and every extracted row were removed." });
      router.push("/");
    },
  });
  return (
    <Dropdown.Root>
      <Dropdown.Trigger asChild>
        <Button size="icon" aria-label="More actions"><MoreHorizontal className="h-4 w-4" /></Button>
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={6} className="z-50 w-56 rounded-xl border border-line bg-surface p-1.5 shadow-pop">
          <Dropdown.Item asChild className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-surface-2">
            <a href={api.pdfUrl(statement.id)} target="_blank" rel="noreferrer"><FileText className="h-4 w-4" /> Open original PDF</a>
          </Dropdown.Item>
          <Dropdown.Item onSelect={() => del.mutate()} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-crit outline-none data-[highlighted]:bg-crit-soft">
            <Trash2 className="h-4 w-4" /> Delete statement & data
          </Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}
