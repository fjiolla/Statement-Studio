"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { Suspense, use, useCallback } from "react";
import { ProcessingView } from "@/components/processing-view";
import { Skeleton } from "@/components/ui";
import { Workspace } from "@/components/workspace";
import { api, type ApiError } from "@/lib/api";

export default function StatementPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["statement", id],
    queryFn: () => api.get(id),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "queued" || s === "processing" ? 4000 : false;
    },
  });
  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["statement", id] });
    qc.invalidateQueries({ queryKey: ["statements"] });
  }, [qc, id]);

  if (q.isLoading) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-4 px-4 py-8 sm:px-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid gap-4 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }
  if (q.isError || !q.data) {
    const e = q.error as ApiError | null;
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-warn" />
        <h1 className="mt-3 text-lg font-semibold text-ink">{e?.status === 404 ? "Statement not found" : "Something went wrong"}</h1>
        <p className="mt-1 text-sm text-ink-2">{e?.status === 404 ? "It may have been deleted, or the 24-hour retention window passed." : e?.message}</p>
        <Link href="/" className="mt-5 inline-block text-sm font-medium text-accent">← Back to statements</Link>
      </div>
    );
  }
  if (q.data.status !== "done") return <ProcessingView key={q.data.status} statement={q.data} onDone={refresh} />;
  return (
    <Suspense>
      <Workspace statement={q.data} />
    </Suspense>
  );
}
