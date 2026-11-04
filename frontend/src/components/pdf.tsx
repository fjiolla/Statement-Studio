"use client";

import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { BBox } from "@/lib/api";
import { cn } from "@/lib/format";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export interface Highlight {
  id: string;
  box: BBox;
  tone: "selected" | "ok" | "mismatch" | "review" | "muted";
  label?: string;
}

const TONE: Record<Highlight["tone"], string> = {
  selected: "bg-[color-mix(in_oklab,var(--accent)_22%,transparent)] ring-2 ring-[var(--accent)]",
  ok: "bg-transparent hover:bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]",
  mismatch: "bg-[color-mix(in_oklab,var(--crit)_14%,transparent)] ring-1 ring-[color-mix(in_oklab,var(--crit)_60%,transparent)]",
  review: "bg-[color-mix(in_oklab,var(--warn)_14%,transparent)]",
  muted: "",
};

function Loading({ h = 200 }: { h?: number }) {
  return (
    <div className="flex items-center justify-center rounded-lg bg-surface-2 text-muted" style={{ height: h }}>
      <Loader2 className="h-5 w-5 animate-spin" />
    </div>
  );
}

/** One full page with clickable row overlays. Coordinates are PDF points in displayed space. */
export function PdfPage({ url, pageIndex, width, highlights, onPick }: {
  url: string; pageIndex: number; width: number; highlights: Highlight[]; onPick?: (id: string) => void;
}) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const scale = size ? width / size.w : 1;
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-white shadow-card" style={{ width, minHeight: size ? size.h * scale : width * 1.3 }}>
      <Document file={url} loading={<Loading h={width * 1.3} />} error={<p className="p-6 text-sm text-crit">Couldn&apos;t load the PDF.</p>}>
        <Page
          pageIndex={pageIndex}
          width={width}
          renderTextLayer={false}
          renderAnnotationLayer={false}
          loading={<Loading h={width * 1.3} />}
          onLoadSuccess={(p) => setSize({ w: p.originalWidth, h: p.originalHeight })}
        />
      </Document>
      {size &&
        highlights.map((h) => (
          <button
            key={h.id}
            onClick={() => onPick?.(h.id)}
            aria-label={h.label ?? "Transaction"}
            title={h.label}
            className={cn("absolute rounded-[3px] transition-colors", TONE[h.tone])}
            style={{ left: h.box.x0 * scale, top: h.box.y0 * scale, width: (h.box.x1 - h.box.x0) * scale, height: (h.box.y1 - h.box.y0) * scale }}
          />
        ))}
    </div>
  );
}

/** A tight crop of one row from the source page: shows exactly what was read. */
export function PdfSnippet({ url, box, width = 520, pad = 14 }: { url: string; box: BBox; width?: number; pad?: number }) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const crop = useMemo(() => {
    const cw = box.x1 - box.x0 + pad * 2;
    const scale = width / cw;
    return { scale, h: (box.y1 - box.y0 + pad * 2) * scale, x: (box.x0 - pad) * scale, y: (box.y0 - pad) * scale };
  }, [box, width, pad]);
  const pageWidth = size ? size.w * crop.scale : width * 2;
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-white" style={{ width, height: crop.h }}>
      <div className="absolute left-0 top-0" style={{ transform: `translate(${-crop.x}px, ${-crop.y}px)` }}>
        <Document file={url} loading={<Loading h={crop.h} />} error={<p className="p-4 text-xs text-crit">Preview unavailable.</p>}>
          <Page
            pageIndex={box.page}
            width={pageWidth}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={null}
            onLoadSuccess={(p) => setSize({ w: p.originalWidth, h: p.originalHeight })}
          />
        </Document>
        {size && (
          <div className="pointer-events-none absolute rounded-[3px] ring-2 ring-[var(--accent)]"
            style={{ left: box.x0 * crop.scale, top: box.y0 * crop.scale, width: (box.x1 - box.x0) * crop.scale, height: (box.y1 - box.y0) * crop.scale, background: "color-mix(in oklab, var(--accent) 8%, transparent)" }} />
        )}
      </div>
    </div>
  );
}
