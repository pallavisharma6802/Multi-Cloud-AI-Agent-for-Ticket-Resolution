"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import TicketTable from "@/components/TicketTable";
import { getOverview, Overview } from "@/lib/api";
export default function Home() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);
  const load = useCallback(() => {
    setLoading(true);
    getOverview(days)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days]);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);
  const total = data?.total || 0,
    resolved = data?.resolved || 0,
    review = data?.needs_review || 0;
  const completed = resolved + review;
  const rate = completed ? Math.round((resolved / completed) * 100) : 0;
  const max = Math.max(...(data?.daily.map((d) => d.total) || [1]), 1);
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR SUPPORT, IN FOCUS</div>
          <h1>Workspace overview</h1>
          <p className="subtle">
            A little less busywork. A lot more resolutions.
          </p>
        </div>
        <div className="button-row">
          <button className="btn" onClick={() => setDays(days === 7 ? 30 : 7)}>
            <Icon name="clock" size={14} />
            Last {days} days⌄
          </button>
          <Link className="btn btn-primary" href="/submit">
            <Icon name="plus" size={15} />
            Create ticket
          </Link>
        </div>
      </div>
      <section className="hero">
        <div>
          <div className="hero-label">
            <Icon name="spark" size={13} /> INTELLIGENT SUPPORT. HUMAN
            OVERSIGHT.
          </div>
          <h2>
            Good support starts
            <br />
            with a clearer picture.
          </h2>
          <p>
            Let your AI agents handle the research. Review their work,
            <br className="hidden md:block" /> understand every decision, and
            move your customers forward.
          </p>
          <Link className="btn btn-primary" href="/triage">
            Open your inbox <Icon name="arrow" size={14} />
          </Link>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit" />
          <div className="orbit two" />
          <div className="art-core">
            <Icon name="spark" size={28} />
          </div>
          <div className="art-chip one">
            <Icon name="check" size={13} />
            Evidence-backed answers
          </div>
          <div className="art-chip two">
            <Icon name="shield" size={13} />
            Human review, when it matters
          </div>
          <div className="art-chip three">
            <span className="dot" />
            Cloud-connected
          </div>
        </div>
      </section>
      {error && (
        <div className="error-box">
          We couldn’t refresh the workspace: {error}{" "}
          <button onClick={load} className="text-link">
            Try again
          </button>
        </div>
      )}
      <div className="stats-grid">
        {[
          {
            label: "Total tickets",
            value: data ? total : "—",
            icon: "inbox",
            foot: `In the last ${days} days`,
          },
          {
            label: "AI resolved",
            value: data ? data.ai_resolved : "—",
            icon: "spark",
            foot: "Completed without human review",
          },
          {
            label: "Needs attention",
            value: data ? review : "—",
            icon: "clock",
            foot: "Waiting for your team",
          },
          {
            label: "Resolution rate",
            value: data ? `${rate}%` : "—",
            icon: "chart",
            foot: "Of completed AI assessments",
          },
        ].map((s) => (
          <div className="stat-card" key={s.label}>
            <div className="stat-top">
              {s.label}
              <span className="stat-icon">
                <Icon name={s.icon} size={15} />
              </span>
            </div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-foot">{s.foot}</div>
          </div>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Ticket activity</h2>
              <p>Your incoming volume and resolutions</p>
            </div>
            <div className="legend">
              <span>
                <i />
                Resolved
              </span>
              <span>
                <i />
                Total
              </span>
            </div>
          </div>
          <div className="panel-body">
            <div className="chart-area">
              {(
                data?.daily ||
                Array.from({ length: days }, (_, i) => ({
                  date: "",
                  total: 0,
                  resolved: 0,
                }))
              ).map((d, i) => (
                <div className="bar-group" key={i}>
                  <span className="bar-tip">
                    {d.total} tickets · {d.resolved} resolved
                  </span>
                  <div
                    className="bar dark"
                    style={{ height: `${(d.resolved / max) * 92}%` }}
                  />
                  <div
                    className="bar"
                    style={{ height: `${(d.total / max) * 92}%` }}
                  />
                </div>
              ))}
            </div>
            <div className="chart-labels">
              {data?.daily.map((d, i) => (
                <span key={d.date}>
                  {days === 7 || i % 5 === 0
                    ? new Date(d.date + "T12:00:00").toLocaleDateString(
                        undefined,
                        {
                          weekday: days === 7 ? "short" : undefined,
                          month: days === 30 ? "short" : undefined,
                          day: days === 30 ? "numeric" : undefined,
                        },
                      )
                    : ""}
                </span>
              ))}
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Resolution breakdown</h2>
              <p>Every ticket has a next step</p>
            </div>
            <Icon name="spark" size={15} />
          </div>
          <div className="panel-body">
            <div
              className="donut"
              style={{
                background: `conic-gradient(#316752 0 ${total ? (resolved / total) * 100 : 0}%,#c9e79f ${total ? (resolved / total) * 100 : 0}% ${total ? ((resolved + review) / total) * 100 : 0}%,#eef2e7 0)`,
              }}
            >
              <div className="donut-inner">
                <strong>{total}</strong>
                <small>Total tickets</small>
              </div>
            </div>
            <div className="metric-row">
              <span>
                <i className="dot" />
                AI resolved
              </span>
              <strong>{resolved}</strong>
            </div>
            <div className="metric-row">
              <span>
                <i className="dot lime" />
                Needs review
              </span>
              <strong>{review}</strong>
            </div>
            <div className="metric-row">
              <span>
                <i className="dot amber" />
                Open tickets
              </span>
              <strong>{data?.open || 0}</strong>
            </div>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Recent tickets</h2>
            <p>The latest conversations in your workspace</p>
          </div>
          <Link href="/triage" className="text-link">
            View all tickets <Icon name="arrow" size={12} />
          </Link>
        </div>
        <TicketTable tickets={data?.recent || []} loading={loading} />
      </section>
      <div className="footer-note">
        <span>Resolve workspace · AI-assisted, evidence-led</span>
        <span>
          {loading
            ? "Refreshing…"
            : data
              ? `Updated ${new Date(data.as_of).toLocaleTimeString()} · Auto-refresh every 30s`
              : "Waiting for connection"}
        </span>
      </div>
    </div>
  );
}
