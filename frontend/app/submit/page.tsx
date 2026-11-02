"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/Icon";
import {
  DomainPack,
  TicketResolutionResponse,
  getDomainPacks,
  submitTicket,
} from "@/lib/api";
const scenarios = [
  {
    title: "I can’t access my account",
    description:
      "I forgot my password and cannot sign in to my account. How can I securely reset it and regain access?",
    tag: "Account access · Routine",
  },
  {
    title: "Duplicate subscription charge",
    description:
      "I was charged twice for the same monthly subscription on my latest invoice. Please help me check the duplicate charge and request a refund.",
    tag: "Billing · Needs investigation",
  },
  {
    title: "Production workspace is unavailable",
    description:
      "Our entire team cannot access the production workspace. Every login returns a 503 error and our customer operations are blocked. This started twenty minutes ago.",
    tag: "Service incident · Urgent",
  },
];
export default function Submit() {
  const [packs, setPacks] = useState<DomainPack[]>([]);
  const [pack, setPack] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState<TicketResolutionResponse | null>(null);
  useEffect(() => {
    getDomainPacks()
      .then((d) => {
        setPacks(d.packs);
        setPack(d.default);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!loading) return;
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [loading]);
  async function send(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setElapsed(0);
    setError("");
    setResult(null);
    try {
      setResult(
        await submitTicket({
          title,
          description,
          user_email: email,
          domain_pack: pack,
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <div className="eyebrow">LET’S FIND A WAY FORWARD</div>
          <h1>Create a ticket</h1>
          <p className="subtle">
            Describe the issue. Your support agents will take it from here.
          </p>
        </div>
        <Link className="btn" href="/triage">
          Back to inbox
        </Link>
      </div>
      <div className="form-layout">
        <div>
          <form className="panel ticket-form" onSubmit={send}>
            <div className="field">
              <label htmlFor="subject">Subject</label>
              <input
                id="subject"
                required
                minLength={5}
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="What can we help with?"
                disabled={loading}
              />
            </div>
            <div className="field">
              <label htmlFor="email">Requester email</label>
              <input
                id="email"
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                disabled={loading}
              />
            </div>
            <div className="field">
              <label htmlFor="domain">Support domain</label>
              <select
                id="domain"
                value={pack}
                onChange={(e) => setPack(e.target.value)}
                disabled={loading || !packs.length}
              >
                {packs.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
              <small>{packs.find((p) => p.id === pack)?.description}</small>
            </div>
            <div className="field">
              <label htmlFor="description">Issue details</label>
              <textarea
                id="description"
                rows={8}
                required
                minLength={10}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Tell us what happened, what you expected, and anything you’ve already tried."
                disabled={loading}
              />
              <small>
                Include error messages and useful context. Please leave out
                passwords and secrets.
              </small>
            </div>
            <div className="form-footer">
              <span className="subtle" style={{ fontSize: 10 }}>
                Your ticket and its decision trail are saved.
              </span>
              <button className="btn btn-primary" disabled={loading || !pack}>
                {loading ? (
                  <>
                    <Icon name="refresh" size={14} className="spinner" />
                    Processing…
                  </>
                ) : (
                  <>
                    Submit ticket <Icon name="arrow" size={14} />
                  </>
                )}
              </button>
            </div>
          </form>
          {loading && (
            <div className="processing" role="status">
              <div className="button-row">
                <Icon name="spark" className="pulse" />
                <strong>Working on your request · {elapsed}s</strong>
              </div>
              <p className="subtle" style={{ marginTop: 12 }}>
                Your agents are classifying the issue, checking knowledge
                sources, and reviewing the response. The result appears here
                when processing is complete.
              </p>
              <p className="subtle" style={{ fontSize: 10 }}>
                Complex requests may take several minutes. This timer shows
                elapsed time, not simulated progress.
              </p>
            </div>
          )}
          {error && (
            <div className="error-box" style={{ marginTop: 20 }}>
              {error}
            </div>
          )}
          {result && (
            <section className="panel detail-card" style={{ marginTop: 20 }}>
              <div
                className="panel-head"
                style={{ padding: 0, marginBottom: 20 }}
              >
                <div>
                  <div className="eyebrow">ASSESSMENT COMPLETE</div>
                  <h2>{result.ticket_id}</h2>
                </div>
                <span
                  className={`badge ${result.requires_human_review ? "amber" : "green"}`}
                >
                  {result.requires_human_review
                    ? "Needs human review"
                    : "AI resolved"}
                </span>
              </div>
              <p className="response-text">
                {result.drafted_response ||
                  "This request needs a support specialist. Open the ticket for the escalation rationale."}
              </p>
              <div className="detail-section">
                <div
                  className="button-row"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="subtle" style={{ fontSize: 10 }}>
                    {Math.round(result.confidence_score * 100)}% confidence ·{" "}
                    {result.processing_time_seconds.toFixed(1)}s
                  </span>
                  <Link className="btn" href={`/tickets/${result.ticket_id}`}>
                    Review full ticket <Icon name="arrow" size={14} />
                  </Link>
                </div>
              </div>
            </section>
          )}
        </div>
        <aside>
          <section className="panel detail-card">
            <div className="eyebrow">NEED A STARTING POINT?</div>
            <h2 style={{ fontSize: 15, fontWeight: 500, margin: "10px 0" }}>
              Try a realistic scenario
            </h2>
            <p className="subtle" style={{ fontSize: 11 }}>
              Select one to fill in the form, then submit it through the live
              agents.
            </p>
            {scenarios.map((s) => (
              <button
                type="button"
                key={s.title}
                className="scenario"
                disabled={loading}
                onClick={() => {
                  setTitle(s.title);
                  setDescription(s.description);
                  if (!email) setEmail("demo@example.com");
                }}
              >
                <strong>{s.title} ↗</strong>
                <small>{s.tag}</small>
              </button>
            ))}
          </section>
          <section className="panel detail-card">
            <div className="eyebrow">WHAT HAPPENS NEXT</div>
            {[
              "Understand the issue",
              "Find relevant evidence",
              "Draft a helpful response",
              "Review and resolve or escalate",
            ].map((s, i) => (
              <div className="step-row" key={s}>
                <span className="step-number">{i + 1}</span>
                {s}
              </div>
            ))}
            <p className="subtle" style={{ fontSize: 10, marginTop: 17 }}>
              Every decision is recorded. Your team can inspect the evidence and
              rationale at any time.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
