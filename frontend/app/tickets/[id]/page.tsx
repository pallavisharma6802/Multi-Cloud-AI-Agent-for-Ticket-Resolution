"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AgentDecisionEntry, TicketTraceResponse, getTicketTrace } from "@/lib/api";

export default function TicketDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<TicketTraceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    getTicketTrace(params.id)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [params?.id]);

  if (error) {
    return <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  }
  if (!data) {
    return <p className="text-sm text-slate-500">Loading trace...</p>;
  }

  const { ticket, agent_decisions, drafted_response } = data;
  const gradeDecision = agent_decisions.find((d) => d.agent_name === "document_grader" && d.action === "grade_documents");
  const gradedDocuments: Array<{ doc_id: string; relevant: boolean; rationale: string; content_preview: string }> =
    gradeDecision?.output?.graded_documents ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-slate-900">{ticket.title}</h1>
          <StatusBadge action={drafted_response?.final_action} requiresHuman={drafted_response?.requires_human_review} />
        </div>
        <p className="mt-1 text-sm text-slate-500">
          {ticket.id} &middot; {ticket.domain_pack} &middot; priority: {ticket.priority} &middot; sentiment:{" "}
          {ticket.sentiment ?? "n/a"} &middot; {new Date(ticket.created_at).toLocaleString()}
        </p>
        <p className="mt-3 whitespace-pre-wrap rounded-md bg-white p-4 text-sm text-slate-700 border border-slate-200">
          {ticket.description}
        </p>
      </div>

      {drafted_response && (
        <Section title="Final Supervisor Decision">
          <p className="text-sm text-slate-700">
            <span className="font-semibold">{drafted_response.final_action}</span> with confidence{" "}
            {(drafted_response.confidence * 100).toFixed(0)}% after {drafted_response.iteration_count ?? 0}{" "}
            loop iteration(s).
          </p>
          {drafted_response.escalation_rationale && (
            <p className="mt-2 rounded-md bg-orange-50 p-3 text-sm text-orange-800">
              <span className="font-semibold">Escalation rationale: </span>
              {drafted_response.escalation_rationale}
            </p>
          )}
          {drafted_response.anomaly_flags && drafted_response.anomaly_flags.length > 0 && (
            <p className="mt-2 rounded-md bg-red-50 p-3 text-sm text-red-800">
              <span className="font-semibold">Engineering safety-net anomalies: </span>
              {drafted_response.anomaly_flags.join("; ")}
            </p>
          )}
          {drafted_response.cost_estimate && (
            <p className="mt-2 text-xs text-slate-500">
              LLM calls: {drafted_response.cost_estimate.llm_call_count} &middot; tokens:{" "}
              {drafted_response.cost_estimate.total_tokens} &middot; latency:{" "}
              {drafted_response.cost_estimate.total_latency_ms}ms
            </p>
          )}
        </Section>
      )}

      {drafted_response?.intent_rationale && (
        <Section title="Intent / Priority Classification">
          <p className="text-sm text-slate-700">
            Intent: <span className="font-medium">{ticket.intent}</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">{drafted_response.intent_rationale}</p>
        </Section>
      )}

      {gradedDocuments.length > 0 && (
        <Section title="CRAG Document Grading (per-document rationale)">
          <div className="space-y-2">
            {gradedDocuments.map((doc) => (
              <div
                key={doc.doc_id}
                className={`rounded-md border p-3 text-sm ${
                  doc.relevant ? "border-green-200 bg-green-50" : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-500">{doc.doc_id}</span>
                  <span className={`text-xs font-semibold ${doc.relevant ? "text-green-700" : "text-slate-500"}`}>
                    {doc.relevant ? "relevant" : "not relevant"}
                  </span>
                </div>
                <p className="mt-1 text-slate-700">{doc.rationale}</p>
                <p className="mt-1 text-xs italic text-slate-400">&ldquo;{doc.content_preview}&hellip;&rdquo;</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {drafted_response?.judge_score_history && drafted_response.judge_score_history.length > 0 && (
        <Section title="Self-RAG Judge Scores (per drafting iteration)">
          <div className="space-y-2">
            {drafted_response.judge_score_history.map((judge, i) => (
              <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
                <p className="font-medium text-slate-800">
                  Iteration {i + 1}: faithfulness {(judge.faithfulness_score * 100).toFixed(0)}%, relevance{" "}
                  {(judge.relevance_score * 100).toFixed(0)}%, confidence {(judge.confidence * 100).toFixed(0)}%
                </p>
                <p className="mt-1 text-slate-600">{judge.rationale}</p>
                {judge.unsupported_claims?.length > 0 && (
                  <p className="mt-1 text-red-700">Unsupported claims: {judge.unsupported_claims.join("; ")}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {drafted_response?.continuation_rationale && drafted_response.continuation_rationale.length > 0 && (
        <Section title="Continuation Agent History">
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
            {drafted_response.continuation_rationale.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </Section>
      )}

      {drafted_response && (
        <Section title="Drafted Response">
          <p className="whitespace-pre-wrap rounded-md bg-white p-4 text-sm text-slate-700 border border-slate-200">
            {drafted_response.draft_text}
          </p>
        </Section>
      )}

      <Section title="Full Agent Decision Log">
        <AgentDecisionTable decisions={agent_decisions} />
      </Section>
    </div>
  );
}

function StatusBadge({ action, requiresHuman }: { action?: string | null; requiresHuman?: boolean }) {
  if (!action) return null;
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-semibold ${
        requiresHuman ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"
      }`}
    >
      {requiresHuman ? "Escalated to human" : "Auto-resolved"}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </div>
  );
}

function AgentDecisionTable({ decisions }: { decisions: AgentDecisionEntry[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2">Agent</th>
            <th className="px-4 py-2">Action</th>
            <th className="px-4 py-2">Confidence</th>
            <th className="px-4 py-2">Timestamp</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {decisions.map((d, i) => (
            <tr key={i} className="align-top hover:bg-slate-50">
              <td className="px-4 py-2 font-medium text-slate-800">{d.agent_name}</td>
              <td className="px-4 py-2 text-slate-600">{d.action}</td>
              <td className="px-4 py-2 text-slate-600">{d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : "-"}</td>
              <td className="px-4 py-2 text-slate-400">{new Date(d.created_at).toLocaleTimeString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
