"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Plus, RefreshCw, Ticket, Sparkles, ShieldCheck, CheckCircle2, ArrowRight, ExternalLink } from "lucide-react";
import { getOverview, listTickets, Overview, TicketSummary } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import TicketRow from "@/components/TicketRow";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3001";
const OUTCOME_COLORS = ["#329dd2", "#ff4c2b", "#f5b942", "#94a3b8"];
const PRIORITY_COLORS: Record<string, string> = {
  urgent: "#dc2626",
  high: "#c2410c",
  medium: "#b45309",
  low: "#0891b2",
};
const CHART_LINE = "#e2e8f0";
const CHART_TICK = { fill: "#64748b", fontSize: 12 };
const CHART_TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  color: "#1a2436",
  fontSize: 13,
  boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
};
const CHART_TOOLTIP_LABEL_STYLE = { color: "#64748b" };

const DASHBOARDS = [
  { uid: "ticket-trends", title: "Ticket Trends" },
  { uid: "agent-performance", title: "Agent Performance" },
  { uid: "ops-cost", title: "Ops & Cost" },
  { uid: "rag-health", title: "RAG Health" },
];

export default function Home() {
  const [data, setData] = useState<Overview | null>(null);
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [days] = useState(30);
  const [dashboard, setDashboard] = useState(DASHBOARDS[0].uid);

  const load = useCallback(() => {
    setLoading(true);
    getOverview(days)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    listTickets({ limit: 500 }).then(setTickets).catch(() => {});
  }, [days]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const outcomeData = [
    { name: "AI answered", value: data?.ai_resolved || 0 },
    { name: "Human resolved", value: data?.human_resolved || 0 },
    { name: "Needs review", value: data?.needs_review || 0 },
    { name: "Open", value: data?.open || 0 },
  ];
  const trendData = (data?.daily || []).map((d) => ({ date: d.date.slice(5), total: d.total, resolved: d.resolved }));

  const priorityData = useMemo(() => {
    const counts: Record<string, number> = { urgent: 0, high: 0, medium: 0, low: 0 };
    tickets.forEach((t) => {
      const p = (t.priority || "").toLowerCase();
      if (p in counts) counts[p] += 1;
    });
    return Object.entries(counts).map(([priority, count]) => ({ priority, count }));
  }, [tickets]);

  const grafanaFull = `${GRAFANA_URL}/d/${dashboard}/${dashboard}?orgId=1&from=now-${days}d&to=now&theme=light&kiosk=tv`;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">VS Code support overview</h1>
          <p className="mt-1 text-sm text-ink-soft">Live ticket volume, outcomes, and diagnostics for the VS Code support workspace.</p>
        </div>
        <Link href="/submit">
          <Button>
            <Plus size={15} /> New ticket
          </Button>
        </Link>
      </div>

      {error && (
        <Card className="mb-6 border-[#fecaca] bg-[#fef2f2] p-4 text-sm text-priority-urgent">
          Couldn&apos;t refresh the workspace: {error}{" "}
          <button onClick={load} className="font-semibold underline">
            Try again
          </button>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={Ticket} label="All tickets" value={data?.total ?? 0} foot={`Last ${days} days`} tone="brand" />
        <StatCard icon={Sparkles} label="AI answered" value={data?.ai_resolved ?? 0} foot="Auto-resolved" tone="purple" />
        <StatCard icon={ShieldCheck} label="Needs review" value={data?.needs_review ?? 0} foot="Waiting on a reviewer" tone="amber" />
        <StatCard icon={CheckCircle2} label="Resolved" value={data?.resolved ?? 0} foot="Closed out" tone="teal" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="p-6 lg:col-span-2">
          <h3 className="text-sm font-semibold text-ink">Tickets created each day</h3>
          <p className="text-xs text-ink-soft">Hover a point for the exact count</p>
          <div className="mt-4 h-64 w-full">
            <ResponsiveContainer>
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#329dd2" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#329dd2" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_LINE} vertical={false} />
                <XAxis dataKey="date" tick={{ ...CHART_TICK, fontSize: 11 }} tickLine={false} axisLine={{ stroke: CHART_LINE }} />
                <YAxis tick={CHART_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={CHART_TOOLTIP_LABEL_STYLE} />
                <Area type="monotone" dataKey="total" stroke="#329dd2" strokeWidth={2} fill="url(#vol)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-sm font-semibold text-ink">Ticket outcomes</h3>
          <p className="text-xs text-ink-soft">{data?.total ?? 0} tickets in this period</p>
          <div className="mt-2 h-56 w-full">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={outcomeData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={3} stroke="none">
                  {outcomeData.map((_, i) => (
                    <Cell key={i} fill={OUTCOME_COLORS[i % OUTCOME_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={CHART_TOOLTIP_LABEL_STYLE} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
            {outcomeData.map((o, i) => (
              <div key={o.name} className="flex items-center gap-1.5 text-ink-soft">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: OUTCOME_COLORS[i] }} />
                {o.name}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="mt-6 p-6">
        <h3 className="text-sm font-semibold text-ink">Volume by priority</h3>
        <p className="text-xs text-ink-soft">Across all tickets in the inbox</p>
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer>
            <BarChart data={priorityData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_LINE} vertical={false} />
              <XAxis dataKey="priority" tick={CHART_TICK} tickLine={false} axisLine={{ stroke: CHART_LINE }} />
              <YAxis tick={CHART_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={CHART_TOOLTIP_LABEL_STYLE} cursor={{ fill: "#32455210" }} />
              <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                {priorityData.map((d, i) => (
                  <Cell key={i} fill={PRIORITY_COLORS[d.priority]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
          <div>
            <h3 className="text-sm font-semibold text-ink">Model &amp; retrieval diagnostics</h3>
            <p className="text-xs text-ink-soft">Confidence, latency, and faithfulness trends, computed in Grafana from the BigQuery fact table.</p>
          </div>
          <div className="flex gap-1 rounded-xl bg-line/60 p-1">
            {DASHBOARDS.map((d) => (
              <button
                key={d.uid}
                onClick={() => setDashboard(d.uid)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  dashboard === d.uid ? "bg-surface text-ink shadow-card" : "text-ink-soft hover:text-ink"
                }`}
              >
                {d.title}
              </button>
            ))}
          </div>
          <a
            href={grafanaFull}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-sm font-semibold text-brand-500 hover:text-brand-600"
          >
            Open in Grafana <ExternalLink size={14} />
          </a>
        </div>
        <iframe
          key={dashboard + days}
          src={grafanaFull}
          className="h-[640px] w-full border-0"
          title={`Grafana: ${dashboard}`}
        />
      </Card>

      <Card className="mt-6">
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-sm font-semibold text-ink">Recent tickets</h2>
          <Link href="/triage" className="flex items-center gap-1 text-sm font-semibold text-brand-500 hover:text-brand-600">
            View inbox <ArrowRight size={13} />
          </Link>
        </div>
        {loading && !data ? (
          <div className="px-6 py-10 text-center text-sm text-ink-soft">Loading recent tickets…</div>
        ) : data && data.recent.length > 0 ? (
          <div>
            {data.recent.map((t) => (
              <TicketRow key={t.ticket_id} ticket={t} />
            ))}
          </div>
        ) : (
          <div className="px-6 py-10 text-center text-sm text-ink-soft">No tickets yet.</div>
        )}
      </Card>

      <div className="mt-6 flex items-center justify-between text-xs text-ink-faint">
        <span>Support workspace</span>
        <span className="flex items-center gap-1.5">
          {loading && <RefreshCw size={12} className="animate-spin" />}
          {loading
            ? "Refreshing…"
            : data
              ? `Updated ${new Date(data.as_of).toLocaleTimeString()} · auto-refresh every 30s`
              : "Waiting for connection"}
        </span>
      </div>
    </div>
  );
}
