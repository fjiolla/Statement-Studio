"use client";

import { motion } from "framer-motion";
import { Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Insights } from "@/lib/api";
import { catMeta } from "@/lib/categories";
import { axisMoney, cn, date, dateShort, money, monthLabel, parseISO, pct } from "@/lib/format";

/* ---------------------------------------------------------------- frame */

export function ChartCard({
  title,
  hint,
  legend,
  table,
  children,
  className,
}: {
  title: string;
  hint?: string;
  legend?: React.ReactNode;
  table?: { head: string[]; rows: (string | number)[][] };
  children: React.ReactNode;
  className?: string;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <div className={cn("card p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
        </div>
        <div className="flex items-center gap-3">
          {legend}
          {table && (
            <button
              onClick={() => setShowTable((s) => !s)}
              className={cn("flex h-7 items-center gap-1 rounded-md px-2 text-xs transition-colors", showTable ? "bg-surface-2 text-ink" : "text-muted hover:text-ink-2")}
              aria-pressed={showTable}
            >
              <Table2 className="h-3.5 w-3.5" /> Table
            </button>
          )}
        </div>
      </div>
      {showTable && table ? (
        <div className="scroll-thin max-h-72 overflow-auto rounded-lg border border-line">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface-2 text-left text-muted">
              <tr>{table.head.map((h, i) => <th key={h} className={cn("px-3 py-2 font-medium", i > 0 && "text-right")}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t border-line">
                  {r.map((c, j) => <td key={j} className={cn("px-3 py-1.5 text-ink-2", j > 0 && "num text-right")}>{c}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </div>
  );
}

function LegendKey({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex items-center gap-3 text-xs text-ink-2">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

function TooltipCard({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="min-w-44 rounded-xl border border-line bg-surface px-3 py-2.5 shadow-pop">
      <p className="mb-1.5 text-xs font-medium text-ink">{title}</p>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 py-0.5 text-xs">
          <span className="flex items-center gap-1.5 text-ink-2">
            {r.color && <span className="h-2 w-2 rounded-[2px]" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span className="num font-medium text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

const axisTick = { fill: "var(--muted)", fontSize: 11 };

/* ---------------------------------------------------------------- cash flow */

export function CashflowChart({ data }: { data: Insights["monthly"] }) {
  const rows = data.filter((d) => d.month !== "unknown").map((d) => ({ ...d, label: monthLabel(d.month) }));
  return (
    <ChartCard
      title="Cash flow by month"
            legend={<LegendKey items={[{ label: "In", color: "var(--series-in)" }, { label: "Out", color: "var(--series-out)" }]} />}
      table={{ head: ["Month", "In", "Out", "Net"], rows: rows.map((r) => [r.label, money(r.inflow), money(r.outflow), money(r.net, { sign: true })]) }}
    >
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%" debounce={120}>
          <BarChart data={rows} barGap={2} margin={{ top: 6, right: 4, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={axisTick} />
            <YAxis tickLine={false} axisLine={false} tick={axisTick} tickFormatter={axisMoney} width={48} />
            <Tooltip
              cursor={{ fill: "var(--surface-2)", radius: 6 } as never}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TooltipCard
                    title={String(label)}
                    rows={[
                      { label: "In", value: money(payload[0].payload.inflow), color: "var(--series-in)" },
                      { label: "Out", value: money(payload[0].payload.outflow), color: "var(--series-out)" },
                      { label: "Net", value: money(payload[0].payload.net, { sign: true }) },
                    ]}
                  />
                ) : null
              }
            />
            <Bar dataKey="inflow" name="In" fill="var(--series-in)" radius={[4, 4, 0, 0]} barSize={22} animationDuration={700} />
            <Bar dataKey="outflow" name="Out" fill="var(--series-out)" radius={[4, 4, 0, 0]} barSize={22} animationDuration={700} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

/* ---------------------------------------------------------------- balance */

export function BalanceChart({ data }: { data: Insights["balance_series"] }) {
  const rows = data.map((d) => ({ ...d, t: parseISO(d.date)!.getTime() }));
  const last = rows[rows.length - 1];
  const min = Math.min(...rows.map((r) => r.balance));
  const max = Math.max(...rows.map((r) => r.balance));
  return (
    <ChartCard
      title="Balance over time"
      hint={last ? `Closing ${money(last.balance)} · low ${money(min)} · high ${money(max)}` : undefined}
      table={{ head: ["Date", "Balance"], rows: rows.map((r) => [date(r.date), money(r.balance)]) }}
    >
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%" debounce={120}>
          <AreaChart data={rows} margin={{ top: 10, right: 12, bottom: 0, left: -8 }}>
            <defs>
              <linearGradient id="balFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.14} />
                <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={axisTick}
              tickFormatter={(t) => new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" }).format(new Date(t))} minTickGap={36} />
            <YAxis tickLine={false} axisLine={false} tick={axisTick} tickFormatter={axisMoney} width={48} domain={["auto", "auto"]} />
            <Tooltip
              cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
              content={({ active, payload }) =>
                active && payload?.length ? <TooltipCard title={date(payload[0].payload.date)} rows={[{ label: "Balance", value: money(payload[0].payload.balance) }]} /> : null
              }
            />
            <Area type="monotone" dataKey="balance" stroke="var(--accent)" strokeWidth={2} fill="url(#balFill)" dot={false}
              activeDot={{ r: 5, fill: "var(--accent)", stroke: "var(--surface)", strokeWidth: 2 }} animationDuration={900} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

/* ---------------------------------------------------------------- categories */

export function CategoryBars({ data, onSelect }: { data: Insights["categories"]; onSelect: (cat: string) => void }) {
  const spend = data.filter((c) => c.kind === "expense" && c.debit > 0).sort((a, b) => b.debit - a.debit);
  const max = spend[0]?.debit || 1;
  const total = spend.reduce((s, c) => s + c.debit, 0);
  return (
    <ChartCard
      title="Spending by category"
      hint={`${money(total, { decimals: false })} total · click a row to filter`}
      table={{ head: ["Category", "Spent", "Share", "Txns"], rows: spend.map((c) => [c.name, money(c.debit), pct(c.share_of_spend, 1), c.count]) }}
    >
      {spend.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">No spending categories in this statement.</p>
      ) : (
        <ul className="space-y-1">
          {spend.slice(0, 9).map((c, i) => {
            const Icon = catMeta(c.category).icon;
            return (
              <li key={c.category}>
                <button onClick={() => onSelect(c.category)} className="group grid w-full grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-surface-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2 text-ink-2 group-hover:text-accent"><Icon className="h-3.5 w-3.5" /></span>
                  <span className="min-w-0">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[13px] text-ink">{c.name}</span>
                      <span className="num shrink-0 text-[11px] text-muted">{pct(c.share_of_spend)} · {c.count}</span>
                    </span>
                    <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-surface-3">
                      <motion.span className="block h-full rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${(c.debit / max) * 100}%` }} transition={{ delay: 0.1 + i * 0.04, duration: 0.7, ease: [0.22, 1, 0.36, 1] }} />
                    </span>
                  </span>
                  <span className="num w-24 text-right text-[13px] font-medium text-ink">{money(c.debit, { decimals: false })}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </ChartCard>
  );
}

/* ---------------------------------------------------------------- calendar heatmap */

export function SpendCalendar({ data, from, to }: { data: Insights["daily_spend"]; from?: string | null; to?: string | null }) {
  const [hover, setHover] = useState<{ date: string; amount: number } | null>(null);
  const { weeks, thresholds, months } = useMemo(() => {
    const amounts = new Map(data.map((d) => [d.date, d.amount]));
    const start = parseISO(from || data[0]?.date) ?? new Date();
    const end = parseISO(to || data[data.length - 1]?.date) ?? new Date();
    const s = new Date(start);
    s.setDate(s.getDate() - ((s.getDay() + 6) % 7)); // Monday
    const weeks: { date: string; amount: number; inRange: boolean }[][] = [];
    const months: { idx: number; label: string }[] = [];
    let cur = new Date(s);
    let lastMonth = -1;
    while (cur <= end && weeks.length < 60) {
      const week = [];
      for (let i = 0; i < 7; i++) {
        const iso = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
        week.push({ date: iso, amount: amounts.get(iso) ?? 0, inRange: cur >= start && cur <= end });
        // label a month in the week that contains its first in-range day
        const firstInRange = cur >= start && cur <= end && (cur.getDate() === 1 || cur.getTime() === start.getTime());
        if (firstInRange && cur.getMonth() !== lastMonth) {
          months.push({ idx: weeks.length, label: new Intl.DateTimeFormat("en-IN", { month: "short" }).format(cur) });
          lastMonth = cur.getMonth();
        }
        cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
      }
      weeks.push(week);
    }
    const vals = data.map((d) => d.amount).filter((v) => v > 0).sort((a, b) => a - b);
    const q = (p: number) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))] ?? 0;
    return { weeks, thresholds: [q(0.2), q(0.4), q(0.6), q(0.8), q(0.95)], months };
  }, [data, from, to]);

  const step = (v: number) => (v <= 0 ? 0 : 1 + thresholds.filter((t) => v > t).length);
  const fills = ["var(--seq-0)", "var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)", "var(--seq-5)", "var(--seq-6)"];

  return (
    <ChartCard
      title="Daily spending"
      hint={hover ? `${date(hover.date)} · ${money(hover.amount)}` : "Excludes transfers"}
      table={{ head: ["Date", "Spent"], rows: data.map((d) => [date(d.date), money(d.amount)]) }}
    >
      <div className="scroll-thin overflow-x-auto pb-1">
        <div className="inline-block">
          <div className="relative mb-1 h-3 pl-6 text-[10px] text-muted">
            {months.map((m) => (
              <span key={m.idx} className="absolute whitespace-nowrap" style={{ left: 24 + m.idx * 17 }}>{m.label}</span>
            ))}
          </div>
          <div className="flex gap-[3px]">
            <div className="mr-1 flex w-5 flex-col gap-[3px] text-[9px] text-muted">
              {["M", "", "W", "", "F", "", "S"].map((d, i) => <span key={i} className="h-[14px] leading-[14px]">{d}</span>)}
            </div>
            {weeks.map((w, i) => (
              <div key={i} className="flex flex-col gap-[3px]">
                {w.map((d) => (
                  <span
                    key={d.date}
                    onMouseEnter={() => d.inRange && setHover(d)}
                    onMouseLeave={() => setHover(null)}
                    title={d.inRange ? `${dateShort(d.date)}: ${money(d.amount)}` : undefined}
                    className={cn("h-[14px] w-[14px] rounded-[3px] transition-transform", d.inRange ? "hover:scale-125" : "opacity-0")}
                    style={{ background: fills[step(d.amount)] }}
                  />
                ))}
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-1.5 pl-6 text-[10px] text-muted">
            Less
            {fills.slice(0, 6).map((f) => <span key={f} className="h-[10px] w-[10px] rounded-[2px]" style={{ background: f }} />)}
            More
          </div>
        </div>
      </div>
    </ChartCard>
  );
}
