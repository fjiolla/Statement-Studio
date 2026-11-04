"use client";

import { motion } from "framer-motion";
import { AlertTriangle, ArrowDownLeft, ArrowUpRight, CalendarClock, Repeat, Scale, Wallet } from "lucide-react";
import type { Statement } from "@/lib/api";
import { catMeta } from "@/lib/categories";
import { cn, date, dateShort, maskAccount, money, moneyCompact } from "@/lib/format";
import { BalanceChart, CashflowChart, CategoryBars, SpendCalendar } from "./charts";
import { Badge, CountUp, ScoreRing, SectionTitle, Tip } from "./ui";

const FIELD_LABELS: [string, string][] = [
  ["account_holder", "Account holder"], ["bank_name", "Bank"], ["account_number", "Account number"], ["card_number", "Card number"],
  ["ifsc", "IFSC"], ["micr", "MICR"], ["branch", "Branch"], ["customer_id", "Customer / CIF ID"], ["account_type", "Account type"],
  ["currency", "Currency"], ["email", "Email"], ["statement_date", "Statement date"], ["period_from", "Period from"], ["period_to", "Period to"],
  ["payment_due_date", "Payment due"], ["credit_limit", "Credit limit"], ["available_credit", "Available credit"], ["cash_limit", "Cash limit"],
  ["total_due", "Total due"], ["minimum_due", "Minimum due"], ["opening_balance", "Opening balance (stated)"], ["closing_balance", "Closing balance (stated)"],
];
const SOURCE_HINT: Record<string, string> = {
  label: "Read next to its label on the statement",
  pattern: "Recognised from its format (e.g. IFSC pattern)",
  inferred: "Inferred from layout; worth a glance",
  derived: "Computed from the transactions",
};

export function Overview({ statement, onFilter, onOpenTxn }: { statement: Statement; onFilter: (f: Record<string, string>) => void; onOpenTxn: (id: string) => void }) {
  const ins = statement.insights!;
  const t = ins.totals;
  const recon = statement.recon!;
  const isCard = statement.statement_type === "credit_card";
  const meta = statement.meta ?? {};

  const tiles = isCard
    ? [
        { label: "Total due", value: (meta.total_due as number) ?? recon.closing_balance ?? 0, icon: Wallet, sub: meta.payment_due_date ? `Due ${date(meta.payment_due_date as string)}` : undefined },
        { label: "Purchases & charges", value: t.outflow, icon: ArrowUpRight, sub: `${t.debit_count} transactions` },
        { label: "Payments & refunds", value: t.inflow, icon: ArrowDownLeft, sub: `${t.credit_count} transactions` },
        { label: "Previous balance", value: recon.opening_balance ?? 0, icon: Scale, sub: meta.minimum_due ? `Minimum due ${money(meta.minimum_due as number)}` : undefined },
      ]
    : [
        { label: "Money in", value: t.inflow, icon: ArrowDownLeft, sub: `${t.credit_count} credits · income ${moneyCompact(t.income)}` },
        { label: "Money out", value: t.outflow, icon: ArrowUpRight, sub: `${t.debit_count} debits · spend ${moneyCompact(t.spend)}` },
        { label: "Net change", value: t.net, icon: Scale, sub: `${money(recon.opening_balance)} → ${money(recon.closing_balance)}`, signed: true },
        { label: "Avg. daily spend", value: t.avg_daily_spend, icon: CalendarClock, sub: `over ${t.span_days} days, excluding transfers` },
      ];

  const largest = ins.largest.map((id) => statement.transactions.find((x) => x.id === id)).filter(Boolean);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[repeat(4,minmax(0,1fr))_minmax(0,1.25fr)]">
        {tiles.map((k, i) => (
          <motion.div key={k.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="card p-5">
            <div className="flex items-center justify-between text-xs text-ink-2">
              {k.label}
              <k.icon className="h-4 w-4 text-muted" />
            </div>
            <div className={cn("mt-3 text-[26px] font-semibold tracking-tight text-ink", "signed" in k && k.signed && k.value < 0 && "text-neg", "signed" in k && k.signed && k.value > 0 && "text-pos")}>
              <CountUp value={k.value} format={(v) => money(v, { sign: "signed" in k && k.signed, decimals: Math.abs(k.value) < 1e5 })} />
            </div>
            {k.sub && <p className="mt-1 truncate text-xs text-muted">{k.sub}</p>}
          </motion.div>
        ))}
        <IntegrityCard statement={statement} />
      </div>

      {statement.warnings && statement.warnings.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl bg-warn-soft p-4">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <ul className="space-y-1 text-sm text-ink">
            {statement.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {ins.monthly.length > 0 && <CashflowChart data={ins.monthly} />}
        {!isCard && ins.balance_series.length > 1 ? <BalanceChart data={ins.balance_series} /> : <CategoryBars data={ins.categories} onSelect={(c) => onFilter({ category: c })} />}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        {!isCard && ins.balance_series.length > 1 && <CategoryBars data={ins.categories} onSelect={(c) => onFilter({ category: c })} />}
        <TopPayees statement={statement} />
        {isCard && <Largest txns={largest as NonNullable<(typeof largest)[number]>[]} onOpen={onOpenTxn} />}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Recurring statement={statement} onFilter={onFilter} />
        {ins.daily_spend.length > 0 ? (
          <SpendCalendar data={ins.daily_spend} from={meta.period_from as string} to={meta.period_to as string} />
        ) : (
          <Largest txns={largest as NonNullable<(typeof largest)[number]>[]} onOpen={onOpenTxn} />
        )}
      </div>

      <div className="card p-5">
        <SectionTitle title="Account details" />
        <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {FIELD_LABELS.filter(([k]) => meta[k] !== undefined && meta[k] !== null && meta[k] !== "").map(([k, label]) => {
            const v = meta[k];
            const src = meta._sources?.[k];
            const shown =
              k === "account_number" ? maskAccount(v as string) :
              typeof v === "number" ? money(v) :
              /date|period/.test(k) ? date(v as string) : String(v);
            return (
              <div key={k} className="flex items-baseline justify-between gap-3 border-b border-line pb-2.5">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="flex min-w-0 items-center gap-2 text-right text-[13px] text-ink">
                  <span className="truncate" title={k === "account_number" ? String(v) : undefined}>{shown}</span>
                  {src && src !== "label" && (
                    <Tip content={SOURCE_HINT[src]}><span><Badge tone={src === "inferred" ? "warn" : "neutral"}>{src}</Badge></span></Tip>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </div>
  );
}

function IntegrityCard({ statement }: { statement: Statement }) {
  const r = statement.recon!;
  const fails = r.checks.filter((c) => c.status === "fail").length;
  const warns = r.checks.filter((c) => c.status === "warn").length;
  const isCard = statement.statement_type === "credit_card";
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card flex items-center gap-4 p-5 sm:col-span-2 xl:col-span-1">
      <ScoreRing score={r.integrity_score} size={84} />
      <div className="min-w-0">
        <p className="text-xs text-ink-2">Reconciliation</p>
        <p className="mt-1 text-sm font-medium text-ink">
          {r.integrity_score === null ? "Not verifiable" : fails === 0 && warns === 0 ? "Everything adds up" : `${fails + warns} check${fails + warns > 1 ? "s" : ""} need attention`}
        </p>
        <p className="num mt-1 text-xs text-muted">
          {isCard ? "Checked against total due" : `${r.ok_rows}/${r.checkable_rows} rows match the balance`}
        </p>
      </div>
    </motion.div>
  );
}

function TopPayees({ statement }: { statement: Statement }) {
  const payees = statement.insights!.top_payees;
  const max = payees[0]?.total || 1;
  return (
    <div className="card p-5">
      <SectionTitle title="Top payees" />
      {payees.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">No identifiable payees.</p>
      ) : (
        <ul className="space-y-2.5">
          {payees.map((p, i) => {
            const Icon = catMeta(p.category).icon;
            return (
              <li key={p.label} className="grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-2 text-[11px] font-semibold text-ink-2">{i + 1}</span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 truncate text-[13px] text-ink">
                    <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
                    <span className="truncate">{p.label}</span>
                  </span>
                  <span className="mt-1 block h-1 overflow-hidden rounded-full bg-surface-3">
                    <motion.span className="block h-full rounded-full bg-[var(--series-out)]" initial={{ width: 0 }} animate={{ width: `${(p.total / max) * 100}%` }} transition={{ delay: i * 0.04, duration: 0.6 }} />
                  </span>
                </span>
                <span className="text-right">
                  <span className="num block text-[13px] font-medium text-ink">{money(p.total, { decimals: false })}</span>
                  <span className="text-[11px] text-muted">{p.count} payment{p.count > 1 ? "s" : ""}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Recurring({ statement, onFilter }: { statement: Statement; onFilter: (f: Record<string, string>) => void }) {
  const groups = statement.recurring ?? [];
  return (
    <div className="card p-5">
      <SectionTitle
        title="Recurring payments"
        action={groups.length ? <button onClick={() => onFilter({ flag: "recurring" })} className="text-xs text-accent hover:underline">View all</button> : undefined}
      />
      {groups.length === 0 ? (
        <div className="flex flex-col items-center py-8 text-center">
          <Repeat className="h-6 w-6 text-muted" />
          <p className="mt-2 text-sm text-ink-2">No recurring payments detected</p>
        </div>
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {groups.slice(0, 7).map((g) => {
            const Icon = catMeta(g.category).icon;
            return (
              <li key={g.id} className="flex items-center gap-3 py-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface-2 text-ink-2"><Icon className="h-4 w-4" /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-ink">{g.label}</p>
                  <p className="text-xs text-muted">
                    <span className="capitalize">{g.cadence}</span> · {g.count}× · last {dateShort(g.last_date)}
                    {g.next_expected && <> · next ~{dateShort(g.next_expected)}</>}
                  </p>
                </div>
                <div className="text-right">
                  <p className={cn("num text-[13px] font-medium", g.direction === "credit" ? "text-pos" : "text-ink")}>
                    {g.direction === "credit" ? "+" : ""}{g.amount_varies ? "~" : ""}{money(g.average_amount, { decimals: g.average_amount < 1000 })}
                  </p>
                  <p className="text-[11px] text-muted">{catMeta(g.category).name}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Largest({ txns, onOpen }: { txns: Statement["transactions"]; onOpen: (id: string) => void }) {
  return (
    <div className="card p-5">
      <SectionTitle title="Largest transactions" />
      <ul className="divide-y divide-[var(--border)]">
        {txns.map((t) => {
          const amt = (t.credit ?? 0) - (t.debit ?? 0);
          return (
            <li key={t.id}>
              <button onClick={() => onOpen(t.id)} className="flex w-full items-center gap-3 py-2.5 text-left hover:opacity-80">
                <span className="w-16 shrink-0 text-xs text-muted">{dateShort(t.date)}</span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{t.merchant || t.counterparty || t.description}</span>
                <span className={cn("num text-[13px] font-medium", amt > 0 ? "text-pos" : "text-ink")}>{money(amt, { sign: true })}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
