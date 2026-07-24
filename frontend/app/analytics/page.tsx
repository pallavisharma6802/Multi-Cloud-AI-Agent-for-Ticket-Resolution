"use client";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3001";

// Dashboard UIDs match grafana/dashboards/*.json's top-level "uid" field --
// see grafana/provisioning/dashboards/dashboards.yaml for how they get
// loaded into the "Ticket Resolution Analytics" folder on Grafana startup.
const DASHBOARDS = [
  {
    uid: "ticket-trends",
    slug: "ticket-trends",
    title: "Ticket Trends",
    description: "Volume over time, by domain pack, by priority, and the 7-day rolling escalation-rate panel.",
  },
  {
    uid: "agent-performance",
    slug: "agent-performance",
    title: "Agent Performance",
    description: "Confidence distributions and the human-override (escalation) rate -- the primary safety-net view.",
  },
  {
    uid: "rag-health",
    slug: "rag-health",
    title: "RAG Health",
    description: "Self-RAG faithfulness/relevance trends and CRAG retrieval-miss rate.",
  },
  {
    uid: "ops-cost",
    slug: "ops-cost",
    title: "Ops & Cost",
    description: "Iterations per ticket, LLM calls/tokens, latency percentiles, and the safety-net trip-wire counter.",
  },
];

export default function AnalyticsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Analytics</h1>
        <p className="mt-1 text-sm text-slate-600">
          Embeds the Grafana dashboards provisioned in <code>grafana/dashboards/</code>, reading from
          BigQuery&apos;s <code>fact_ticket_events</code> table (see{" "}
          <code>app/analytics/bigquery_sink.py</code>). Requires{" "}
          <code>docker compose up grafana</code> with real GCP credentials configured -- see{" "}
          <code>grafana/README.md</code>. If the panels below don&apos;t load, that setup step hasn&apos;t
          been done yet in this environment.
        </p>
      </div>

      {DASHBOARDS.map((d) => (
        <div key={d.uid} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-slate-900">{d.title}</h2>
              <p className="text-sm text-slate-500">{d.description}</p>
            </div>
            <a
              href={`${GRAFANA_URL}/d/${d.uid}/${d.slug}?orgId=1&from=now-30d&to=now`}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-indigo-600 hover:underline"
            >
              Open in Grafana &rarr;
            </a>
          </div>
          <iframe
            src={`${GRAFANA_URL}/d/${d.uid}/${d.slug}?orgId=1&from=now-30d&to=now&kiosk=tv&theme=light`}
            className="h-[500px] w-full rounded-md border border-slate-100"
            title={d.title}
          />
        </div>
      ))}
    </div>
  );
}
