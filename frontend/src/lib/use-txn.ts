"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Statement, type Txn } from "./api";
import { catMeta } from "./categories";

function patchCache(qc: ReturnType<typeof useQueryClient>, sid: string, updated: Partial<Txn>[]) {
  qc.setQueryData<Statement>(["statement", sid], (s) => {
    if (!s) return s;
    const byId = new Map(updated.map((u) => [u.id, u]));
    return { ...s, transactions: s.transactions.map((t) => (byId.has(t.id) ? { ...t, ...byId.get(t.id) } : t)) };
  });
}

/** Category changes: optimistic, then offers to apply to similar payees and to remember the rule. */
export function useRecategorise(sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ txn, category }: { txn: Txn; category: string }) => {
      const res = await api.patchTxn(txn.id, { category });
      const similar = txn.key ? await api.similar(txn.id) : { count: 0, ids: [] };
      return { res, similar };
    },
    onMutate: ({ txn, category }) => {
      patchCache(qc, sid, [{ id: txn.id, category, category_name: catMeta(category).name, method: "user", confidence: 1, needs_review: false, reviewed: true }]);
    },
    onSuccess: ({ res, similar }, { txn, category }) => {
      patchCache(qc, sid, res.updated);
      const name = catMeta(category).name;
      const who = txn.merchant || txn.counterparty || "this payee";
      const others = similar.count;
      toast.success(`Moved to ${name}`, {
        description: others > 0 ? `${others} other transaction${others > 1 ? "s" : ""} with ${who} found.` : `Saved. Future statements will learn from it.`,
        duration: 8000,
        action:
          others > 0
            ? {
                label: `Apply to ${others}`,
                onClick: async () => {
                  const r = await api.patchTxn(txn.id, { category, apply_to_similar: true, remember: true });
                  patchCache(qc, sid, r.updated);
                  qc.invalidateQueries({ queryKey: ["statement"] });
                  toast(`Updated ${r.count - 1} more and remembered “${who}” → ${name}`);
                },
              }
            : {
                label: "Always",
                onClick: async () => {
                  await api.patchTxn(txn.id, { category, remember: true });
                  toast(`Remembered “${who}” → ${name}`, { description: "Applied automatically to future uploads." });
                },
              },
      });
      qc.invalidateQueries({ queryKey: ["statements"] });
    },
    onError: (e: Error) => {
      toast.error("Couldn't save", { description: e.message });
      qc.invalidateQueries({ queryKey: ["statement", sid] });
    },
  });
}

export function useMarkReviewed(sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (txn: Txn) => api.patchTxn(txn.id, { reviewed: true }),
    onMutate: (txn) => patchCache(qc, sid, [{ id: txn.id, reviewed: true }]),
    onSuccess: (r) => patchCache(qc, sid, r.updated),
  });
}

export function useAcceptSuggestion(sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (txn: Txn) => api.acceptSuggestion(txn.id),
    onSuccess: (t) => {
      patchCache(qc, sid, [t]);
      toast.success("Correction applied", { description: "The row now reconciles with its neighbours." });
    },
    onError: (e: Error) => toast.error("Couldn't apply", { description: e.message }),
  });
}

export function useNote(sid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ txn, note }: { txn: Txn; note: string }) => api.patchTxn(txn.id, { note }),
    onSuccess: (r) => patchCache(qc, sid, r.updated),
  });
}
