"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { catMeta } from "@/lib/categories";
import { pct, relativeTime } from "@/lib/format";

const STEPS = [
  ["Your rules", "Payees you corrected before"],
  ["Banking rules", "Salary, interest, charges, ATM, EMI, tax, reversals"],
  ["Merchant list", "220+ Indian merchants and billers"],
  ["ML model", "TF-IDF + logistic regression for unknown shops"],
  ["Payment channel", "UPI to a person → transfer, merchant QR → purchase"],
];

type Card = {
  training_examples?: number; user_corrections?: number; corrections_available?: number; trained_at?: string;
  holdout?: { accuracy: number; macro_f1: number };
  benchmark?: { hybrid_accuracy: number; ml_only_accuracy: number };
};

export default function ModelPage() {
  const qc = useQueryClient();
  const card = useQuery({ queryKey: ["model"], queryFn: api.model });
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const retrain = useMutation({
    mutationFn: api.retrain,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["model"] }); toast.success("Model retrained with your corrections"); },
    onError: (e: Error) => toast.error("Retraining failed", { description: e.message }),
  });
  const delRule = useMutation({ mutationFn: api.deleteRule, onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });
  const c = (card.data ?? {}) as Card;

  return (
    <div className="mx-auto max-w-[900px] px-4 py-12 sm:px-6">
      <h1 className="text-[28px] font-semibold tracking-tight text-ink">Classifier</h1>
      <p className="mt-2 text-[15px] text-ink-2">No LLMs. Each transaction goes through these layers in order; the first confident one decides.</p>

      <ol className="mt-8 divide-y divide-[var(--border)] border-y border-line">
        {STEPS.map(([t, d], i) => (
          <li key={t} className="flex items-baseline gap-4 py-3">
            <span className="num w-5 text-sm text-muted">{i + 1}</span>
            <span className="w-40 shrink-0 text-sm font-medium text-ink">{t}</span>
            <span className="text-sm text-ink-2">{d}</span>
          </li>
        ))}
      </ol>

      <div className="mt-10 grid gap-4 sm:grid-cols-3">
        {card.isLoading ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />) : (
          <>
            <Metric value={c.benchmark ? pct(c.benchmark.hybrid_accuracy, 1) : "—"} label="Hybrid, real narrations*" />
            <Metric value={c.benchmark ? pct(c.benchmark.ml_only_accuracy, 1) : "—"} label="ML alone, same set" />
            <Metric value={c.holdout ? pct(c.holdout.accuracy, 1) : "—"} label="ML, unseen names (blind)" />
          </>
        )}
      </div>
      <p className="mt-3 text-xs text-muted">*161 hand-labelled rows from 8 real statements. Also used while writing rules, so it&apos;s a regression check, not a blind test.</p>

      <div className="mt-12 flex items-center justify-between gap-4 border-y border-line py-4">
        <div>
          <p className="text-sm font-medium text-ink">Retrain on your corrections</p>
          <p className="mt-0.5 text-xs text-muted">
            {c.corrections_available ?? 0} collected · last trained {c.trained_at ? new Date(c.trained_at).toLocaleDateString("en-IN") : "—"}
          </p>
        </div>
        <Button size="sm" onClick={() => retrain.mutate()} loading={retrain.isPending} disabled={!c.corrections_available}>
          <RefreshCcw className="h-3.5 w-3.5" /> Retrain
        </Button>
      </div>

      <h2 className="mt-12 text-sm font-semibold text-ink">Learned rules</h2>
      {rules.data?.length ? (
        <ul className="mt-3 divide-y divide-[var(--border)] border-y border-line">
          {rules.data.map((r) => {
            const M = catMeta(r.category);
            return (
              <li key={r.id} className="flex items-center gap-3 py-2.5">
                <M.icon className="h-4 w-4 text-muted" />
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{r.label || r.match}</span>
                <span className="text-xs text-ink-2">{r.category_name}</span>
                <span className="hidden w-16 text-right text-xs text-muted sm:block">{relativeTime(r.created_at)}</span>
                <Button size="icon" variant="danger" onClick={() => delRule.mutate(r.id)} aria-label={`Delete rule for ${r.label}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted">None yet. Correct a category and choose “Apply to similar” or “Always”.</p>
      )}
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="card p-5">
      <p className="text-[30px] font-semibold tracking-tight text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-2">{label}</p>
    </div>
  );
}
