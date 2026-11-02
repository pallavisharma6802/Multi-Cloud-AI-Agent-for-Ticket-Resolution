"use client";
import { useState } from "react";
import Icon from "@/components/Icon";
const BASE = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3001";
const boards = [
  {
    uid: "ticket-trends",
    title: "Ticket trends",
    sub: "Volume & escalation",
    icon: "chart",
  },
  {
    uid: "agent-performance",
    title: "Agent performance",
    sub: "Confidence & decisions",
    icon: "spark",
  },
  {
    uid: "rag-health",
    title: "Knowledge quality",
    sub: "Relevance & faithfulness",
    icon: "shield",
  },
  {
    uid: "ops-cost",
    title: "Operations",
    sub: "Latency & token usage",
    icon: "bolt",
  },
];
export default function Analytics() {
  const [active, setActive] = useState(0);
  const [range, setRange] = useState("7d");
  const [version, setVersion] = useState(0);
  const b = boards[active];
  const url = `${BASE}/d/${b.uid}/${b.uid}?orgId=1&from=now-${range}&to=now&refresh=30s&theme=light`;
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <div className="eyebrow">FROM ACTIVITY TO INSIGHT</div>
          <h1>Support analytics</h1>
          <p className="subtle">
            Understand your volume, your agents, and the quality of every
            answer.
          </p>
        </div>
        <div className="button-row">
          <select
            className="btn"
            aria-label="Analytics time range"
            value={range}
            onChange={(e) => setRange(e.target.value)}
          >
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
          <button
            className="btn"
            aria-label="Refresh dashboard"
            onClick={() => setVersion((v) => v + 1)}
          >
            <Icon name="refresh" size={14} />
          </button>
        </div>
      </div>
      <div className="cloud-strip">
        <Icon name="cloud" size={16} />
        <span>
          Cloud analytics · BigQuery ticket events · Grafana dashboards
        </span>
        <a
          className="text-link"
          style={{ marginLeft: "auto" }}
          href={url}
          target="_blank"
          rel="noreferrer"
        >
          Open Grafana <Icon name="external" size={12} />
        </a>
      </div>
      <div className="dashboard-options">
        {boards.map((d, i) => (
          <button
            key={d.uid}
            onClick={() => setActive(i)}
            className={`dashboard-option ${active === i ? "active" : ""}`}
          >
            <Icon name={d.icon} size={20} />
            <span>
              <strong>{d.title}</strong>
              <small>{d.sub}</small>
            </span>
          </button>
        ))}
      </div>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>{b.title}</h2>
            <p>Live queries against your cloud event history</p>
          </div>
          <span className="badge green">Refreshes every 30s</span>
        </div>
        <iframe
          key={`${active}-${range}-${version}`}
          className="analytics-frame"
          title={b.title}
          src={`${url}&kiosk=tv`}
        />
      </section>
      <div className="footer-note">
        <span>Switch views above to explore all four dashboards.</span>
        <span>Queries use the selected time range.</span>
      </div>
    </div>
  );
}
