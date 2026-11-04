"use client";

import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, FileUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import { LottieAnim } from "./lottie";

const MAX_MB = 40;
const ENGINES = [
  { id: "rapidocr", name: "RapidOCR", note: "Best on low-quality scans" },
  { id: "tesseract", name: "Tesseract", note: "Classic, less accurate" },
] as const;

export function UploadZone() {
  const router = useRouter();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [drag, setDrag] = useState(false);
  const [engine, setEngine] = useState<(typeof ENGINES)[number]["id"]>("rapidocr");

  const upload = useMutation({
    mutationFn: (file: File) => api.upload(file, { ocrEngine: engine }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      if (r.duplicate) toast("Already uploaded — opening it");
      router.push(`/statements/${r.id}`);
    },
    onError: (e: ApiError) => toast.error("Upload failed", { description: e.message }),
  });

  const accept = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (!file) return;
      if (!(file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))) {
        toast.error("Only PDF statements are supported");
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.error(`File is over ${MAX_MB} MB`);
        return;
      }
      upload.mutate(file);
    },
    [upload],
  );

  const busy = upload.isPending;
  return (
    <div>
      <div
        onDragEnter={(e) => { e.preventDefault(); depth.current += 1; setDrag(true); }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => { depth.current -= 1; if (depth.current <= 0) setDrag(false); }}
        onDrop={(e) => { e.preventDefault(); depth.current = 0; setDrag(false); accept(e.dataTransfer.files); }}
        className={cn(
          "rounded-xl border border-dashed bg-surface transition-colors duration-200",
          drag ? "border-accent bg-accent-soft" : "border-line-strong hover:border-[var(--text-2)]",
        )}
      >
        <button
          type="button"
          onClick={() => input.current?.click()}
          disabled={busy}
          className="flex w-full flex-col items-center px-6 py-14 text-center outline-none"
          aria-label="Upload a statement PDF"
        >
          <div className="flex h-16 w-16 items-center justify-center">
            {drag || busy ? (
              <LottieAnim name="upload" className="h-16 w-16" fallback={<FileUp className="h-7 w-7 text-accent" />} />
            ) : (
              <FileUp className="h-7 w-7 text-ink-2" strokeWidth={1.6} />
            )}
          </div>
          <p className="mt-3 text-[15px] font-medium text-ink">{busy ? "Uploading…" : drag ? "Drop to upload" : "Drop a PDF statement here"}</p>
          <p className="mt-1 text-sm text-muted">
            or <span className="text-accent-ink underline decoration-[var(--border-strong)] underline-offset-4">choose a file</span> · up to {MAX_MB} MB
          </p>
        </button>
        <input ref={input} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => { accept(e.target.files); e.target.value = ""; }} />
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>Password-protected files are fine — you&apos;ll be asked.</span>
        <Popover.Root>
          <Popover.Trigger asChild>
            <button className="flex items-center gap-1 hover:text-ink-2">
              OCR: {ENGINES.find((e) => e.id === engine)!.name} <ChevronDown className="h-3 w-3" />
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content align="end" sideOffset={6} className="z-50 w-56 rounded-lg border border-line bg-surface p-1 shadow-pop">
              {ENGINES.map((e) => (
                <button key={e.id} onClick={() => setEngine(e.id)} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left hover:bg-surface-2">
                  <span className="flex-1">
                    <span className="block text-sm text-ink">{e.name}</span>
                    <span className="text-xs text-muted">{e.note}</span>
                  </span>
                  {engine === e.id && <Check className="h-4 w-4 text-accent" />}
                </button>
              ))}
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>
    </div>
  );
}
