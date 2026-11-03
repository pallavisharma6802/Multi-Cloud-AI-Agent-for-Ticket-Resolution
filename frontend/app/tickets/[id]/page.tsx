"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Sparkles,
  Copy,
  Check,
  ChevronDown,
  Clock,
  ShieldCheck,
} from "lucide-react";
import { TicketTraceResponse, getTicketTrace, retryTicket, resolveTicket } from "@/lib/api";
import { Card, Button, PriorityBadge, StatusBadge } from "@/components/ui";

const TABS = [
  { id: "conversation", label: "Conversation" },
  { id: "trace", label: "Agent activity" },
  { id: "evidence", label: "Knowledge & quality" },
];

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TicketTraceResponse | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("conversation");
  const [copied, setCopied] = useState(false);
  const [working, setWorking] = useState(false);
  const [actionError, setActionError] = useState("");

  async function act(action: "retry" | "resolve") {
    setWorking(true);
    setActionError("");
    try {
      if (action === "retry") await retryTicket(id);
      else await resolveTicket(id);
      setData(await getTicketTrace(id));
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setWorking(false);
    }
  }

  useEffect(() => {
    getTicketTrace(id).then(setData).catch((e) => setError(e.message));
  }, [id]);

  if (error)
    return (
      <Card className="border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
        {error}
        <Link href="/triage" className="ml-3 font-semibold underline">
          Back to inbox
        </Link>
      </Card>
    );
  if (!data)
    return <Card className="p-10 text-center text-sm text-ink-soft">Loading ticket and decision trail…</Card>;

  const { ticket: t, drafted_response: r, agent_decisions: decisions } = data;
  const relevant = decisions.flatMap((d) => d.output?.graded_documents || []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(r?.draft_text || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Clipboard is unavailable. You can select and copy the response text.");
    }
  }

  return (
    <div>
      <Link href="/triage" className="mb-5 flex items-center gap-1.5 text-sm font-medium text-ink-soft hover:text-ink">
        <ArrowLeft size={15} /> Back to inbox
      </Link>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
            {t.id} · {(t.domain_pack || "Support").replaceAll("_", " ")}
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{t.title}</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Opened {new Date(t.created_at + (/Z$/.test(t.created_at) ? "" : "Z")).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={t.status} />
      </div>

      {actionError && <Card className="mb-5 border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{actionError}</Card>}

      {t.status === "open" && (
        <Card className="mb-6 flex items-center gap-3 border-brand-100 bg-brand-50 p-4 text-sm text-brand-700">
          <Clock size={16} />
          <span>This ticket hasn&apos;t finished processing. Retry it to resume using the same ticket ID.</span>
          <Button className="ml-auto" disabled={working} onClick={() => act("retry")}>
            {working ? "Processing…" : "Retry assessment"}
          </Button>
        </Card>
      )}
      {t.status === "needs_review" && (
        <Card className="mb-6 flex items-center gap-3 border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
          <ShieldCheck size={16} />
          <span>Needs your team&apos;s review. After checking the response, mark it resolved.</span>
          <Button className="ml-auto" disabled={working} onClick={() => act("resolve")}>
            {working ? "Saving…" : "Mark resolved"}
          </Button>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <div className="mb-5 flex gap-1 rounded-xl bg-slate-100 p-1">
            {TABS.map((v) => (
              <button
                key={v.id}
                onClick={() => setTab(v.id)}
                className={`rounded-lg px-3.5 py-2 text-sm font-medium transition ${
                  tab === v.id ? "bg-surface text-ink shadow-card" : "text-ink-soft hover:text-ink"
                }`}
              >
                {v.label}
                {v.id === "trace" && ` (${decisions.length})`}
              </button>
            ))}
          </div>

          {tab === "conversation" && (
            <div className="space-y-5">
              <Card className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Customer request</div>
                <p className="mt-3 text-sm leading-relaxed text-ink">{t.description}</p>
              </Card>
              <Card className="p-6">
                <div className="mb-5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-500 text-white">
                      <Sparkles size={16} />
                    </span>
                    <div>
                      <h2 className="text-sm font-semibold text-ink">AI response</h2>
                      <p className="text-xs text-ink-soft">Grounded in your knowledge sources</p>
                    </div>
                  </div>
                  {r?.draft_text && (
                    <Button variant="secondary" onClick={copy} className="py-1.5">
                      {copied ? <Check size={14} /> : <Copy size={14} />}
                      {copied ? "Copied" : "Copy"}
                    </Button>
                  )}
                </div>
                <p className="text-sm leading-relaxed text-ink">
                  {r?.draft_text || "No response was drafted. This ticket requires a support specialist."}
                </p>
                {r?.escalation_rationale && (
                  <div className="mt-5 border-t border-line pt-5">
                    <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Why this needs a person</div>
                    <p className="mt-2 text-sm text-ink-soft">{r.escalation_rationale}</p>
                  </div>
                )}
                {r?.intent_rationale && (
                  <div className="mt-5 border-t border-line pt-5">
                    <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">How we understood the issue</div>
                    <p className="mt-2 text-sm text-ink-soft">{r.intent_rationale}</p>
                  </div>
                )}
              </Card>
            </div>
          )}

          {tab === "trace" && (
            <Card className="p-6">
              <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">A complete decision trail</div>
              <p className="mb-5 mt-2 text-sm text-ink-soft">Expand any step to inspect its recorded inputs, outputs, and rationale.</p>
              <div className="space-y-2">
                {decisions.map((d, i) => (
                  <details key={i} className="group rounded-xl border border-line">
                    <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3">
                      <span>
                        <strong className="block text-sm font-medium capitalize text-ink">
                          {d.agent_name.replaceAll("_", " ")}
                        </strong>
                        <small className="text-xs text-ink-soft">
                          {d.action.replaceAll("_", " ")} ·{" "}
                          {d.confidence === null ? "no confidence reported" : `${Math.round(d.confidence * 100)}% confidence`}
                        </small>
                      </span>
                      <ChevronDown size={15} className="shrink-0 text-ink-faint transition group-open:rotate-180" />
                    </summary>
                    <pre className="overflow-x-auto border-t border-line bg-slate-50 p-4 text-xs text-ink-soft">
                      {JSON.stringify(d.output, null, 2)}
                    </pre>
                  </details>
                ))}
              </div>
            </Card>
          )}

          {tab === "evidence" && (
            <div className="space-y-5">
              <Card className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Supporting knowledge</div>
                {r?.kb_documents?.length ? (
                  <div className="mt-3 space-y-2">
                    {r.kb_documents.map((d) => (
                      <details key={d.doc_id} className="rounded-xl border border-line p-4" open>
                        <summary className="flex cursor-pointer list-none items-center justify-between text-sm">
                          <span className="truncate text-ink-soft">{String(d.metadata?.source || d.doc_id)}</span>
                          <span className="shrink-0 rounded-full bg-teal-100 px-2 py-0.5 text-xs font-semibold text-teal-500">
                            {Math.round(d.similarity_score * 100)}% match
                          </span>
                        </summary>
                        <p className="mt-3 text-sm leading-relaxed text-ink">{d.content}</p>
                      </details>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-ink-soft">No supporting documents were attached to this response.</p>
                )}
                {relevant.length > 0 && (
                  <div className="mt-5 border-t border-line pt-5">
                    <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Document relevance review</div>
                    {relevant.map((d: any, i: number) => (
                      <div key={i} className="mt-3">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                            d.relevant ? "bg-teal-100 text-teal-500" : "bg-amber-50 text-amber-600"
                          }`}
                        >
                          {d.relevant ? "Relevant" : "Excluded"}
                        </span>
                        <p className="mt-1.5 text-sm text-ink-soft">{d.rationale}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
              <Card className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Response quality checks</div>
                {r?.judge_score_history?.length ? (
                  <div className="mt-3 space-y-4">
                    {r.judge_score_history.map((j, i) => (
                      <div key={i} className="border-t border-line pt-4 first:border-0 first:pt-0">
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-ink-soft">Review {i + 1}</span>
                          <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-semibold text-teal-500">
                            {Math.round((j.faithfulness_score || 0) * 100)}% faithful
                          </span>
                          <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-500">
                            {Math.round((j.relevance_score || 0) * 100)}% relevant
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-ink-soft">{j.rationale}</p>
                        {j.unsupported_claims?.length > 0 && (
                          <div className="mt-2 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700">
                            Claims to check: {j.unsupported_claims.join("; ")}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-ink-soft">No quality scores are available for this ticket.</p>
                )}
              </Card>
            </div>
          )}
        </div>

        <aside className="space-y-5">
          <Card className="p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Ticket details</div>
            <div className="mt-3 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Status</span>
                <StatusBadge status={t.status} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Priority</span>
                <PriorityBadge priority={t.priority} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Intent</span>
                <strong className="max-w-[140px] truncate text-right capitalize text-ink">
                  {t.intent?.replaceAll("_", " ") || "Unclassified"}
                </strong>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Sentiment</span>
                <strong className="capitalize text-ink">{t.sentiment || "Not available"}</strong>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Assessment</div>
            <div className="mt-2 text-4xl font-semibold tracking-tight text-ink">
              {r ? Math.round(r.confidence * 100) : "—"}
              <span className="text-lg text-ink-faint">%</span>
            </div>
            <p className="text-xs text-ink-soft">Supervisor confidence</p>
            <div className="mt-4 space-y-3 border-t border-line pt-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">LLM calls</span>
                <strong className="text-ink">{r?.cost_estimate?.llm_call_count ?? "—"}</strong>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Tokens used</span>
                <strong className="text-ink">{r?.cost_estimate?.total_tokens?.toLocaleString() ?? "—"}</strong>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-soft">Review loops</span>
                <strong className="text-ink">{r?.iteration_count ?? "—"}</strong>
              </div>
            </div>
          </Card>

          <Card className="flex items-center gap-3 border-teal-100 bg-teal-100/40 p-4 text-sm text-teal-700">
            <ShieldCheck size={18} />
            <span>Decision trail recorded with this ticket.</span>
          </Card>
        </aside>
      </div>
    </div>
  );
}
