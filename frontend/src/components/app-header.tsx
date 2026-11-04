"use client";

import { motion } from "framer-motion";
import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CommandPalette } from "./command-palette";
import { Kbd } from "./ui";
import { cn } from "@/lib/format";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2" aria-label="Statement Studio home">
      <span className="brand-mark h-[22px] w-[22px] text-accent" aria-hidden />
      <span className="text-[15px] font-semibold tracking-tight text-ink">Statement Studio</span>
    </Link>
  );
}

const NAV = [
  { href: "/", label: "Statements" },
  { href: "/model", label: "Classifier" },
];

export function AppHeader() {
  const path = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-line bg-bg">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4 sm:px-6">
          <Logo />
          <nav className="hidden items-center gap-1 sm:flex">
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" || path.startsWith("/statements") : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href} className={cn("relative rounded-lg px-3 py-1.5 text-sm transition-colors", active ? "text-ink" : "text-ink-2 hover:text-ink")}>
                  {active && <motion.span layoutId="nav-pill" className="absolute inset-x-3 -bottom-[13px] h-[2px] rounded-full bg-ink" />}
                  <span className="relative">{n.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setOpen(true)}
              className="hidden h-8 w-56 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-muted transition-colors hover:text-ink-2 md:flex"
            >
              <Search className="h-4 w-4" />
              Search
              <span className="ml-auto flex gap-1">
                <Kbd>⌘</Kbd>
                <Kbd>K</Kbd>
              </span>
            </button>
            <button
              onClick={() => setOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-[10px] text-ink-2 hover:bg-surface-2 md:hidden"
              aria-label="Search"
            >
              <Search className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>
      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}
