"use client";

import * as Popover from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import type { Txn } from "@/lib/api";
import { CATEGORY_META, catMeta } from "@/lib/categories";
import { cn } from "@/lib/format";

const GROUPS: [string, "income" | "expense" | "transfer"][] = [["Spending", "expense"], ["Income", "income"], ["Transfers & savings", "transfer"]];

export function CategoryPill({ txn, onPick, size = "md" }: { txn: Txn; onPick: (cat: string) => void; size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  const meta = catMeta(txn.category);
  const Icon = meta.icon;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "group inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface-2 text-ink transition-colors hover:border-line-strong hover:bg-surface-3",
            size === "sm" ? "h-6 px-2 text-[11.5px]" : "h-7 px-2.5 text-xs",
            txn.needs_review && !txn.reviewed && "border-[color-mix(in_oklab,var(--warn)_45%,transparent)]",
          )}
          aria-label={`Category: ${meta.name}. Change`}
        >
          <Icon className="h-3.5 w-3.5 shrink-0 text-ink-2" />
          <span className="truncate">{meta.name}</span>
          <ChevronDown className="h-3 w-3 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="start" sideOffset={6} onClick={(e) => e.stopPropagation()} className="z-[70] w-72 overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
          <CategoryCommand
            txn={txn}
            onPick={(c) => {
              setOpen(false);
              if (c !== txn.category) onPick(c);
            }}
          />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function CategoryCommand({ txn, onPick }: { txn: Txn; onPick: (cat: string) => void }) {
  const isDebit = (txn.debit ?? 0) > 0;
  const suggested = (txn.alternatives ?? []).filter((a) => a.category !== txn.category && a.score >= 0.05).slice(0, 2);
  const item = "flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13px] text-ink data-[selected=true]:bg-surface-2";
  const heading = "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:text-muted";
  return (
    <Command label="Choose a category" loop>
      <Command.Input autoFocus placeholder="Search categories…" className="h-10 w-full border-b border-line bg-transparent px-3 text-sm text-ink outline-none placeholder:text-muted" />
      <Command.List className="scroll-thin max-h-80 overflow-y-auto p-1.5">
        <Command.Empty className="py-6 text-center text-sm text-muted">No category found.</Command.Empty>
        {suggested.length > 0 && (
          <Command.Group heading="Model suggests" className={heading}>
            {suggested.map((a) => {
              const M = catMeta(a.category);
              return (
                <Command.Item key={`s-${a.category}`} value={`suggest ${M.name}`} onSelect={() => onPick(a.category)} className={item}>
                  <M.icon className="h-3.5 w-3.5 text-ink-2" />
                  <span className="flex-1">{M.name}</span>
                  <span className="num text-[11px] text-muted">{Math.round(a.score * 100)}%</span>
                </Command.Item>
              );
            })}
          </Command.Group>
        )}
        {(isDebit ? GROUPS : [GROUPS[1], GROUPS[2], GROUPS[0]]).map(([label, kind]) => (
          <Command.Group key={kind} heading={label} className={heading}>
            {Object.entries(CATEGORY_META)
              .filter(([, m]) => m.kind === kind)
              .map(([id, m]) => (
                <Command.Item key={id} value={m.name} onSelect={() => onPick(id)} className={item}>
                  <m.icon className="h-3.5 w-3.5 text-ink-2" />
                  <span className="flex-1">{m.name}</span>
                  {id === txn.category && <Check className="h-3.5 w-3.5 text-accent" />}
                </Command.Item>
              ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command>
  );
}
