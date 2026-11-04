export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type StatementStatus = "queued" | "processing" | "needs_password" | "done" | "failed";
export type StatementType = "bank_account" | "credit_card";

export interface BBox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Txn {
  id: string;
  statement_id: string;
  idx: number;
  date: string | null;
  value_date: string | null;
  raw_date: string | null;
  description: string;
  reference: string | null;
  debit: number | null;
  credit: number | null;
  balance: number | null;
  category: string;
  category_name: string;
  model_category: string;
  confidence: number;
  method: string;
  explanation: string;
  merchant: string | null;
  counterparty: string | null;
  channel: string | null;
  vpa: string | null;
  key: string | null;
  needs_review: boolean;
  reviewed: boolean;
  self_transfer: boolean;
  alternatives: { category: string; name: string; score: number }[];
  flags: string[];
  notes: string[];
  bboxes: BBox[];
  suggestion: { field: "balance" | "amount"; value: number; direction?: string; reason: string } | null;
  recon_status: "ok" | "mismatch" | "corrected" | "unverified";
  direction_source: string;
  source: "text" | "ocr";
  ocr_confidence: number | null;
  recurring_id: string | null;
  user_note: string | null;
  page: number;
}

export interface Check {
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  detail: string;
}

export interface Recon {
  order: string;
  checkable_rows: number;
  ok_rows: number;
  corrected_rows: number;
  mismatched_rows: number;
  opening_balance: number | null;
  opening_source: string;
  closing_balance: number | null;
  total_debits: number;
  total_credits: number;
  integrity_score: number | null;
  checks: Check[];
}

export interface PageInfo {
  index: number;
  kind: "text" | "scanned" | "hybrid" | "empty";
  width: number;
  height: number;
  char_count: number;
  image_coverage: number;
  ocr_engine: string | null;
  ocr_confidence: number | null;
  ocr_seconds: number | null;
  hidden_words: number;
  words: number;
}

export interface Recurring {
  id: string;
  label: string;
  category: string;
  direction: "debit" | "credit";
  cadence: string;
  average_amount: number;
  count: number;
  first_date: string;
  last_date: string;
  next_expected: string | null;
  txn_indices: number[];
  amount_varies: boolean;
}

export interface Insights {
  totals: {
    inflow: number;
    outflow: number;
    net: number;
    income: number;
    spend: number;
    transfers_in: number;
    transfers_out: number;
    self_transfers: number;
    count: number;
    debit_count: number;
    credit_count: number;
    avg_daily_spend: number;
    span_days: number;
  };
  categories: {
    category: string;
    name: string;
    kind: string;
    icon: string;
    debit: number;
    credit: number;
    count: number;
    share_of_spend: number | null;
  }[];
  monthly: { month: string; inflow: number; outflow: number; spend: number; income: number; net: number }[];
  balance_series: { date: string; balance: number }[];
  daily_spend: { date: string; amount: number }[];
  top_payees: { label: string; total: number; count: number; category: string }[];
  channels: { channel: string; outflow: number }[];
  largest: string[];
  review_ids: string[];
  flagged_ids: string[];
}

export type Meta = Record<string, string | number | null> & { _sources?: Record<string, string> };

export interface Statement {
  id: string;
  created_at: number;
  filename: string;
  status: StatementStatus;
  error_code: string | null;
  error: string | null;
  statement_type: StatementType | null;
  document_type: "text" | "scanned" | "mixed" | null;
  bank_name: string | null;
  page_count: number | null;
  ocr_engine: string | null;
  meta: Meta | null;
  recon: Recon | null;
  pages: PageInfo[] | null;
  warnings: string[] | null;
  timings: Record<string, number> | null;
  columns: { role: string; label: string }[] | null;
  recurring: Recurring[] | null;
  is_sample: boolean;
  transactions: Txn[];
  insights: Insights | null;
}

export interface StatementSummary {
  id: string;
  created_at: number;
  filename: string;
  status: StatementStatus;
  error: string | null;
  error_code: string | null;
  statement_type: StatementType | null;
  document_type: string | null;
  bank_name: string | null;
  page_count: number | null;
  transactions: number;
  review_count: number;
  account_holder: string | null;
  account_number: string | null;
  period_from: string | null;
  period_to: string | null;
  integrity_score: number | null;
  is_sample: boolean;
  overlaps_with?: string[];
}

export interface Category {
  id: string;
  name: string;
  kind: "income" | "expense" | "transfer";
  icon: string;
}

export interface Sample {
  file: string;
  title: string;
  kind: string;
  pages: number;
  tag: string;
}

export interface ProgressEvent {
  stage: string;
  message?: string;
  page?: number;
  total?: number;
  kind?: string;
  confidence?: number;
  seconds?: number;
  code?: string;
  seq?: number;
  transactions?: number;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Is the API running?");
  }
  if (!res.ok) {
    let code = "http_" + res.status;
    let message = res.statusText || "Request failed";
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      } else if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ ok: boolean; retention_hours: number; max_upload_mb: number }>("/api/health"),
  categories: () => request<Category[]>("/api/categories"),
  samples: () => request<Sample[]>("/api/samples"),
  loadSample: (file: string) => request<{ id: string; duplicate: boolean }>(`/api/samples/${encodeURIComponent(file)}`, { method: "POST" }),
  list: () => request<StatementSummary[]>("/api/statements"),
  get: (id: string) => request<Statement>(`/api/statements/${id}`),
  upload: (file: File, opts: { password?: string; ocrEngine?: string } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.password) fd.append("password", opts.password);
    fd.append("ocr_engine", opts.ocrEngine || "rapidocr");
    return request<{ id: string; status: string; duplicate: boolean }>("/api/statements", { method: "POST", body: fd });
  },
  password: (id: string, password: string) => request<{ id: string; status: string }>(`/api/statements/${id}/password`, json({ password })),
  remove: (id: string) => request<{ deleted: string }>(`/api/statements/${id}`, { method: "DELETE" }),
  patchTxn: (id: string, body: { category?: string; apply_to_similar?: boolean; remember?: boolean; note?: string; reviewed?: boolean }) =>
    request<{ updated: Txn[]; count: number }>(`/api/transactions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  similar: (id: string) => request<{ ids: string[]; count: number }>(`/api/transactions/${id}/similar`),
  acceptSuggestion: (id: string) => request<Txn>(`/api/transactions/${id}/accept-suggestion`, { method: "POST" }),
  model: () => request<Record<string, unknown>>("/api/model"),
  retrain: () => request<Record<string, unknown>>("/api/model/retrain", { method: "POST" }),
  rules: () => request<{ id: number; match: string; kind: string; category: string; category_name: string; direction: string | null; label: string | null; created_at: number }[]>("/api/rules"),
  deleteRule: (id: number) => request<{ deleted: number }>(`/api/rules/${id}`, { method: "DELETE" }),
  pdfUrl: (id: string) => `${API_URL}/api/statements/${id}/pdf`,
  eventsUrl: (id: string) => `${API_URL}/api/statements/${id}/events`,
  exportUrl: (ids: string[], format: "xlsx" | "csv", onlyReview = false) =>
    `${API_URL}/api/export?ids=${ids.join(",")}&format=${format}${onlyReview ? "&only_review=true" : ""}`,
};
