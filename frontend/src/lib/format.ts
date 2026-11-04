import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹1,20,749.89 — Indian digit grouping */
export function money(v: number | null | undefined, opts: { sign?: boolean; decimals?: boolean } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = (opts.decimals === false ? inr0 : inr2).format(Math.abs(v));
  const sign = v < 0 ? "−" : opts.sign && v > 0 ? "+" : "";
  return `${sign}₹${s}`;
}

/** Compact Indian units: ₹4.2K, ₹1.25L, ₹3.1Cr */
export function moneyCompact(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(a >= 1e8 ? 1 : 2)}Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(a >= 1e6 ? 1 : 2)}L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(a >= 1e4 ? 0 : 1)}K`;
  return `${sign}₹${inr0.format(a)}`;
}

export function axisMoney(v: number) {
  const a = Math.abs(v);
  if (a >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `${(v / 1e5).toFixed(a >= 1e6 ? 0 : 1)}L`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${v}`;
}

const dFmt = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const dShort = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short" });
const mFmt = new Intl.DateTimeFormat("en-IN", { month: "short", year: "2-digit" });

export function parseISO(s: string | null | undefined) {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
export function date(s: string | null | undefined) {
  const d = parseISO(s);
  return d ? dFmt.format(d) : "—";
}
export function dateShort(s: string | null | undefined) {
  const d = parseISO(s);
  return d ? dShort.format(d) : "—";
}
export function monthLabel(ym: string) {
  const d = parseISO(`${ym}-01`);
  return d ? mFmt.format(d) : ym;
}
export function relativeTime(epochSeconds: number) {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function maskAccount(v: string | number | null | undefined) {
  if (!v) return "—";
  const s = String(v).replace(/\s/g, "");
  if (s.length <= 4) return s;
  return `•••• ${s.slice(-4)}`;
}

export function pct(v: number | null | undefined, digits = 0) {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
