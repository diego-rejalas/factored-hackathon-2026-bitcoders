export type Language = "es" | "pt";

export type DemoScenario = {
  scenario: "auto_resolved" | "ambiguous" | "fraud" | "threshold";
  customer_id: string;
  document_number: string;
  first_name: string;
  hint_es: string;
  hint_pt: string;
};

export type Candidate = {
  transaction_id: string;
  merchant_name?: string | null;
  amount_usd_effective?: number | string | null;
  amount?: number | string | null;
  currency?: string | null;
  transaction_date?: string | null;
  transaction_status?: string | null;
};

export type Handoff = {
  case_id?: string;
  reason?: string;
  limitation?: string;
  request?: { es?: string; pt?: string };
  customer_language?: Language;
  conversation_id?: string;
  verified_facts?: string[];
  actions_taken?: Array<Record<string, unknown>>;
  evidence?: Array<Record<string, unknown>>;
  open_questions?: string[];
};

export type DisputeCase = {
  case_id: string;
  customer_id?: string;
  transaction_id: string | null;
  reason_code: string;
  summary?: string;
  status: string;
  evidence?: Record<string, unknown>;
  created_at?: string;
  resolved_at?: string | null;
  events?: CaseEvent[];
  handoff?: Handoff | null;
  conversation_id?: string | null;
};

export type CaseEvent = {
  event: string;
  payload?: Record<string, unknown>;
  ts?: string;
};

export type ChatResponse = {
  reply: string;
  conversation_id: string;
  outcome: "resolved" | "clarify" | "escalated";
  handoff?: Handoff | null;
  candidates?: Candidate[] | null;
  case?: DisputeCase | null;
  reason?: string | null;
  language?: Language | null;
};

export type ConversationItem = {
  conversation_id: string;
  title: string;
  last_at: string;
};

export type StoredMessage = {
  role: "user" | "bot";
  text: string;
  response?: ChatResponse | null;
  created_at: string;
};

export type CaseListItem = Pick<
  DisputeCase,
  "case_id" | "transaction_id" | "reason_code" | "status" | "created_at" | "resolved_at"
>;

export type AdminCaseItem = CaseListItem & {
  customer_id: string;
  first_name?: string | null;
  last_name?: string | null;
  country?: string | null;
  handoff_reason?: string | null;
  customer_language?: string | null;
};

export type TraceRow = {
  ts?: string;
  node: string;
  intent?: string | null;
  tool?: string | null;
  result_status?: string | null;
  latency_ms?: number | null;
};

export type BackendMetrics = {
  window_hours: number | null;
  total_cases: number;
  by_status: Record<string, number>;
  safe_automated_resolution: {
    resolved: number;
    attempted: number;
    rate_percent: number | null;
  };
  escalations: { count: number; rate_percent: number | null };
  human_closure: { closed: number };
  by_language: Array<{ language: string; n: number }>;
  by_reason: Array<{ reason: string; n: number }>;
};

export type AgentMetrics = {
  tracing_enabled: boolean;
  window_hours?: number | null;
  runs_by_outcome?: Record<string, number>;
  total_runs?: number;
  containment?: {
    conversations: number;
    without_transfer: number;
    rate_percent: number | null;
  };
  latency_by_node?: Record<string, { p50_ms: number | null; p95_ms: number | null; n: number }>;
  intents?: Record<string, number>;
  languages?: Record<string, number>;
  verify?: { ok: number; failed: number };
};

export type DataFreshness = {
  gold: { customers: number; transactions: number; snapshot_edge: string | null };
  app: { disputes: number };
  last_etl_run: Record<string, unknown> | null;
};

export function formatDate(value: string | null | undefined, language: Language): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat(language === "pt" ? "pt-BR" : "es-419", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

export function formatAmount(value: number | string | null | undefined, language: Language): string {
  if (value === null || value === undefined || value === "") return "-";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return new Intl.NumberFormat(language === "pt" ? "pt-BR" : "es-419", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatCandidateAmount(candidate: Candidate, language: Language): string {
  if (candidate.amount_usd_effective !== null && candidate.amount_usd_effective !== undefined) {
    return formatAmount(candidate.amount_usd_effective, language);
  }
  if (candidate.amount === null || candidate.amount === undefined) return "-";
  const amount = Number(candidate.amount);
  const currency = candidate.currency;
  if (!Number.isFinite(amount) || !currency) {
    return `${candidate.amount}${currency ? ` ${currency}` : ""}`;
  }
  try {
    return new Intl.NumberFormat(language === "pt" ? "pt-BR" : "es-419", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${candidate.amount} ${currency}`;
  }
}
