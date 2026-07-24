// Fetch helpers for FastAPI routes in app/api/routes/tickets.py.

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DomainPack {
  id: string;
  display_name: string;
  description: string;
  intent_eval_available: boolean;
}

export interface KBDocument {
  doc_id: string;
  content: string;
  similarity_score: number;
  metadata: Record<string, unknown>;
}

export interface TicketResolutionResponse {
  ticket_id: string;
  status: string;
  drafted_response: string;
  confidence_score: number;
  supporting_documents: KBDocument[];
  processing_time_seconds: number;
  requires_human_review: boolean;
  trace: Record<string, any>;
}

export interface TicketSummary {
  ticket_id: string;
  title: string;
  description: string;
  user_email: string;
  status: string;
  priority: string;
  intent: string | null;
  domain_pack: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentDecisionEntry {
  agent_name: string;
  action: string;
  output: Record<string, any>;
  confidence: number | null;
  created_at: string;
}

export interface TicketTraceResponse {
  ticket: {
    id: string;
    title: string;
    description: string;
    status: string;
    priority: string;
    intent: string | null;
    sentiment: string | null;
    domain_pack: string | null;
    created_at: string;
  };
  agent_decisions: AgentDecisionEntry[];
  drafted_response: {
    draft_text: string;
    confidence: number;
    requires_human_review: boolean;
    iteration_count: number | null;
    intent_rationale: string | null;
    escalation_rationale: string | null;
    final_action: string | null;
    judge_score_history: Array<Record<string, any>> | null;
    continuation_rationale: string[] | null;
    anomaly_flags: string[] | null;
    cost_estimate: Record<string, any> | null;
    kb_documents: KBDocument[] | null;
  } | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse failure, fall back to statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function getDomainPacks(): Promise<{ packs: DomainPack[]; default: string }> {
  return apiFetch("/api/v1/domain-packs");
}

export function submitTicket(data: {
  title: string;
  description: string;
  user_email: string;
  category?: string;
  domain_pack?: string;
}): Promise<TicketResolutionResponse> {
  return apiFetch("/api/v1/tickets", { method: "POST", body: JSON.stringify(data) });
}

export function listTickets(filters: {
  status_filter?: string;
  priority_filter?: string;
  domain_pack_filter?: string;
  limit?: number;
} = {}): Promise<TicketSummary[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== "") params.set(k, String(v));
  });
  const qs = params.toString();
  return apiFetch(`/api/v1/tickets${qs ? `?${qs}` : ""}`);
}

export function getTicketTrace(ticketId: string): Promise<TicketTraceResponse> {
  return apiFetch(`/api/v1/tickets/${ticketId}/trace`);
}
