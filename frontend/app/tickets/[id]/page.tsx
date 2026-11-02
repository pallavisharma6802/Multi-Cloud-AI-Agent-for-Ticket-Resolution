"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Icon from "@/components/Icon";
import { Status, Priority } from "@/components/TicketTable";
import { TicketTraceResponse, getTicketTrace, retryTicket, resolveTicket } from "@/lib/api";
export default function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TicketTraceResponse | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("conversation");
  const [copied, setCopied] = useState(false);
  const [working, setWorking] = useState(false);
  const [actionError, setActionError] = useState("");
  async function act(action:"retry"|"resolve") {
    setWorking(true); setActionError("");
    try { if(action==="retry") await retryTicket(id); else await resolveTicket(id); setData(await getTicketTrace(id)); }
    catch(e:any){setActionError(e.message)} finally{setWorking(false)}
  }
  useEffect(() => {
    getTicketTrace(id)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);
  if (error)
    return (
      <div className="error-box">
        {error}
        <Link className="btn" href="/triage">
          Back to inbox
        </Link>
      </div>
    );
  if (!data)
    return (
      <section className="panel">
        <div className="empty-state">Loading ticket and decision trail…</div>
      </section>
    );
  const { ticket: t, drafted_response: r, agent_decisions: decisions } = data;
  const relevant = decisions.flatMap((d) => d.output?.graded_documents || []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(r?.draft_text || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(
        "Clipboard is unavailable. You can select and copy the response text.",
      );
    }
  }
  return (
    <div className="page-enter">
      <Link href="/triage" className="text-link" style={{ marginBottom: 20 }}>
        ← Back to inbox
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {t.id} · {(t.domain_pack || "Support").replaceAll("_", " ")}
          </div>
          <h1 style={{ fontSize: 25 }}>{t.title}</h1>
          <p className="subtle">
            Opened{" "}
            {new Date(
              t.created_at + (/Z$/.test(t.created_at) ? "" : "Z"),
            ).toLocaleString()}
          </p>
        </div>
        <Status status={t.status} />
      </div>
      {actionError&&<div className="error-box">{actionError}</div>}
      {t.status==="open"&&<div className="cloud-strip"><Icon name="clock" size={16}/><span>This ticket has not finished processing. Retry it to resume an assessment using the same ticket ID.</span><button className="btn btn-primary" style={{marginLeft:"auto"}} disabled={working} onClick={()=>act("retry")}>{working?"Processing…":"Retry assessment"}</button></div>}
      {t.status==="in_progress"&&<div className="cloud-strip"><Icon name="shield" size={16}/><span>This ticket needs your team’s review. After checking the response and addressing the request, mark it resolved.</span><button className="btn btn-primary" style={{marginLeft:"auto"}} disabled={working} onClick={()=>act("resolve")}>{working?"Saving…":"Mark resolved"}</button></div>}
      <div className="ticket-layout">
        <div>
          <div className="tabs detail-tabs">
            {[
              { id: "conversation", label: "Conversation" },
              { id: "trace", label: `Agent activity (${decisions.length})` },
              { id: "evidence", label: "Knowledge & quality" },
            ].map((v) => (
              <button
                className={`tab ${tab === v.id ? "active" : ""}`}
                key={v.id}
                onClick={() => setTab(v.id)}
              >
                {v.label}
              </button>
            ))}
          </div>
          {tab === "conversation" && (
            <>
              <section className="panel detail-card">
                <div className="detail-label">CUSTOMER REQUEST</div>
                <p className="response-text">{t.description}</p>
              </section>
              <section className="panel detail-card">
                <div
                  className="panel-head"
                  style={{ padding: 0, marginBottom: 22 }}
                >
                  <div className="button-row">
                    <span className="stat-icon">
                      <Icon name="spark" size={16} />
                    </span>
                    <div>
                      <h2>AI response</h2>
                      <p>Grounded in your knowledge sources</p>
                    </div>
                  </div>
                  {r?.draft_text && (
                    <button className="btn" onClick={copy}>
                      <Icon name={copied ? "check" : "copy"} size={13} />
                      {copied ? "Copied" : "Copy"}
                    </button>
                  )}
                </div>
                <p className="response-text">
                  {r?.draft_text ||
                    "No response was drafted. This ticket requires a support specialist."}
                </p>
                {r?.escalation_rationale && (
                  <div className="detail-section">
                    <div className="detail-label">WHY THIS NEEDS A PERSON</div>
                    <p className="response-text">{r.escalation_rationale}</p>
                  </div>
                )}
                {r?.intent_rationale && (
                  <div className="detail-section">
                    <div className="detail-label">
                      HOW WE UNDERSTOOD THE ISSUE
                    </div>
                    <p className="response-text">{r.intent_rationale}</p>
                  </div>
                )}
              </section>
            </>
          )}
          {tab === "trace" && (
            <section className="panel detail-card">
              <div className="detail-label">A COMPLETE DECISION TRAIL</div>
              <p className="subtle" style={{ marginBottom: 26 }}>
                Expand any step to inspect its recorded inputs, outputs, and
                rationale.
              </p>
              {decisions.map((d, i) => (
                <details className="timeline-item" key={i}>
                  <summary>
                    <span>
                      <strong
                        style={{
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        {d.agent_name.replaceAll("_", " ")}
                      </strong>
                      <small>
                        {d.action.replaceAll("_", " ")} ·{" "}
                        {d.confidence === null
                          ? "No confidence reported"
                          : `${Math.round(d.confidence * 100)}% confidence`}
                      </small>
                    </span>
                    <Icon name="chevron" size={13} />
                  </summary>
                  <pre>{JSON.stringify(d.output, null, 2)}</pre>
                </details>
              ))}
            </section>
          )}
          {tab === "evidence" && (
            <>
              <section className="panel detail-card">
                <div className="detail-label">SUPPORTING KNOWLEDGE</div>
                {r?.kb_documents?.length ? (
                  r.kb_documents.map((d) => (
                    <details key={d.doc_id} className="detail-section" open>
                      <summary style={{ cursor: "pointer", fontSize: 12 }}>
                        {String(d.metadata?.source || d.doc_id)}
                        <span
                          className="badge green"
                          style={{ float: "right" }}
                        >
                          {Math.round(d.similarity_score * 100)}% match
                        </span>
                      </summary>
                      <p className="response-text" style={{ marginTop: 15 }}>
                        {d.content}
                      </p>
                    </details>
                  ))
                ) : (
                  <p className="subtle">
                    No supporting documents were attached to this response.
                  </p>
                )}
                {relevant.length > 0 && (
                  <div className="detail-section">
                    <div className="detail-label">
                      DOCUMENT RELEVANCE REVIEW
                    </div>
                    {relevant.map((d: any, i: number) => (
                      <div className="detail-section" key={i}>
                        <span
                          className={`badge ${d.relevant ? "green" : "amber"}`}
                        >
                          {d.relevant ? "Relevant" : "Excluded"}
                        </span>
                        <p className="subtle" style={{ marginTop: 10 }}>
                          {d.rationale}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </section>
              <section className="panel detail-card">
                <div className="detail-label">RESPONSE QUALITY CHECKS</div>
                {r?.judge_score_history?.length ? (
                  r.judge_score_history.map((j, i) => (
                    <div key={i} className="detail-section">
                      <div className="button-row">
                        <span className="badge">Review {i + 1}</span>
                        <span className="badge green">
                          {Math.round((j.faithfulness_score || 0) * 100)}%
                          faithful
                        </span>
                        <span className="badge blue">
                          {Math.round((j.relevance_score || 0) * 100)}% relevant
                        </span>
                      </div>
                      <p className="response-text" style={{ marginTop: 12 }}>
                        {j.rationale}
                      </p>
                      {j.unsupported_claims?.length > 0 && (
                        <div className="error-box">
                          Claims to check: {j.unsupported_claims.join("; ")}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="subtle">
                    No quality scores are available for this ticket.
                  </p>
                )}
              </section>
            </>
          )}
        </div>
        <aside>
          <section className="panel detail-card">
            <div className="detail-label">TICKET DETAILS</div>
            <div className="metric-row">
              <span>Status</span>
              <Status status={t.status} />
            </div>
            <div className="metric-row">
              <span>Priority</span>
              <Priority priority={t.priority} />
            </div>
            <div className="metric-row">
              <span>Intent</span>
              <strong
                style={{ fontSize: 10, maxWidth: 130, textAlign: "right" }}
              >
                {t.intent?.replaceAll("_", " ") || "Unclassified"}
              </strong>
            </div>
            <div className="metric-row">
              <span>Sentiment</span>
              <strong style={{ fontSize: 10 }}>
                {t.sentiment || "Not available"}
              </strong>
            </div>
          </section>
          <section className="panel detail-card">
            <div className="detail-label">ASSESSMENT</div>
            <div style={{ fontSize: 34, fontWeight: 500, letterSpacing: -1 }}>
              {r ? Math.round(r.confidence * 100) : "—"}
              <span style={{ fontSize: 16, color: "#91a083" }}>%</span>
            </div>
            <p className="subtle" style={{ fontSize: 10, marginTop: 5 }}>
              Supervisor confidence
            </p>
            <div className="detail-section">
              <div className="metric-row">
                <span>LLM calls</span>
                <strong>{r?.cost_estimate?.llm_call_count ?? "—"}</strong>
              </div>
              <div className="metric-row">
                <span>Tokens used</span>
                <strong>
                  {r?.cost_estimate?.total_tokens?.toLocaleString() ?? "—"}
                </strong>
              </div>
              <div className="metric-row">
                <span>Review loops</span>
                <strong>{r?.iteration_count ?? "—"}</strong>
              </div>
            </div>
          </section>
          <div className="cloud-strip">
            <Icon name="shield" size={18} />
            <span>Decision trail recorded with this ticket.</span>
          </div>
        </aside>
      </div>
    </div>
  );
}
