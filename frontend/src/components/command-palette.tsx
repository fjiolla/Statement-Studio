"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueries } from "@tanstack/react-query";
import { Command } from "cmdk";
import { FileText, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { catMeta } from "@/lib/categories";
import { dateShort, money } from "@/lib/format";

/** ⌘K — jump to any statement or find any transaction across all of them. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["statements"], queryFn: api.list, enabled: open });
  const done = (list.data ?? []).filter((s) => s.status === "done").slice(0, 8);
  const details = useQueries({
    queries: done.map((s) => ({ queryKey: ["statement", s.id], queryFn: () => api.get(s.id), enabled: open, staleTime: 60_000 })),
  });

  const matches = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (term.length < 2) return [];
    const out: { sid: string; id: string; label: string; date: string | null; amount: number; cat: string }[] = [];
    for (const d of details) {
      for (const t of d.data?.transactions ?? []) {
        const hay = `${t.description} ${t.merchant ?? ""} ${t.counterparty ?? ""} ${t.category_name}`.toLowerCase();
        if (hay.includes(term)) {
          out.push({ sid: t.statement_id, id: t.id, label: t.merchant || t.counterparty || t.description, date: t.date, amount: (t.credit ?? 0) - (t.debit ?? 0), cat: t.category });
          if (out.length >= 40) return out;
        }
      }
    }
    return out;
  }, [q, details]);

  const go = (href: string) => {
    onOpenChange(false);
    setQ("");
    router.push(href);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-[14vh] z-[61] w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-surface shadow-pop">
          <Dialog.Title className="sr-only">Search</Dialog.Title>
          <Command shouldFilter={false} label="Search statements and transactions">
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Search className="h-4 w-4 text-muted" />
              <Command.Input
                value={q}
                onValueChange={setQ}
                placeholder="Search merchants, payees, categories…"
                className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
              />
            </div>
            <Command.List className="scroll-thin max-h-[52vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-8 text-center text-sm text-muted">
                {q.length < 2 ? "Type to search across every statement." : "No matching transactions."}
              </Command.Empty>
              {q.length < 2 && done.length > 0 && (
                <Command.Group heading="Statements" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-muted">
                  {done.map((s) => (
                    <Command.Item key={s.id} value={s.id} onSelect={() => go(`/statements/${s.id}`)} className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm text-ink data-[selected=true]:bg-surface-2">
                      <FileText className="h-4 w-4 text-muted" />
                      <span className="truncate">{s.bank_name || s.filename}</span>
                      <span className="ml-auto text-xs text-muted">{s.transactions} txns</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {matches.length > 0 && (
                <Command.Group heading="Transactions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-muted">
                  {matches.map((m) => {
                    const Icon = catMeta(m.cat).icon;
                    return (
                      <Command.Item key={m.id} value={m.id} onSelect={() => go(`/statements/${m.sid}?tab=transactions&txn=${m.id}`)} className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm data-[selected=true]:bg-surface-2">
                        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2 text-ink-2">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <span className="min-w-0 flex-1 truncate text-ink">{m.label}</span>
                        <span className="text-xs text-muted">{dateShort(m.date)}</span>
                        <span className={`num w-28 text-right text-sm ${m.amount >= 0 ? "text-pos" : "text-ink"}`}>{money(m.amount, { sign: true })}</span>
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
