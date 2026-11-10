"use client";
import { useEffect, useMemo, useState } from "react";
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
  Legend,
  ResponsiveContainer,
} from "recharts";
import { ExternalLink } from "lucide-react";
import { getOverview, listTickets, Overview, TicketSummary } from "@/lib/api";
import { Card, PageHeading, Button } from "@/components/ui";

const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3001";
const OUTCOME_COLORS = ["#245bdb", "#2fb6a3", "#d9a441", "#8a98ac"];
const PRIORITY_COLORS: Record<string, string> = {
  urgent: "#dd5a5a",
  high: "#e0843f",
  medium: "#d9a441",
  low: "#2fb6a3",
};

const DASHBOARDS = [
  { uid: "ticket-trends", title: "Ticket Trends" },
  { uid: "agent-performance", title: "Agent Performance" },
  { uid: "ops-cost", title: "Ops & Cost" },
  { uid: "rag-health", title: "RAG Health" },
];

function ChartCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Card className="p-6">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {subtitle && <p className="text-xs text-ink-soft">{subtitle}</p>}
      <div className="mt-4 h-72 w-full">{children}</div>
    </Card>
  );
}

export default function Analytics() {
  const [data, setData] = useState<Overview | null>(null);
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [days, setDays] = useState(30);
  const [dashboard, setDashboard] = useState(DASHBOARDS[0].uid);
  const [error, setError] = useState("");

  useEffect(() => {
    getOverview(days)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message));
    listTickets({ limit: 500 }).then(setTickets).catch(() => {});
  }, [days]);

  const outcomeData = useMemo(
    () => [
      { name: "AI answered", value: data?.ai_resolved || 0 },
      { name: "Human resolved", value: data?.human_resolved || 0 },
      { name: "Needs review", value: data?.needs_review || 0 },
      { name: "Open", value: data?.open || 0 },
    ],
    [data]
  );

  const priorityData = useMemo(() => {
    const counts: Record<string, number> = { urgent: 0, high: 0, medium: 0, low: 0 };
    tickets.forEach((t) => {
      const p = (t.priority || "").toLowerCase();
      if (p in counts) counts[p] += 1;
    });
    return Object.entries(counts).map(([priority, count]) => ({ priority, count }));
  }, [tickets]);

  const trendData = useMemo(
    () => (data?.daily || []).map((d) => ({ date: d.date.slice(5), total: d.total, resolved: d.resolved })),
    [data]
  );

  const grafanaFull = `${GRAFANA_URL}/d/${dashboard}/${dashboard}?orgId=1&from=now-${days}d&to=now&theme=light&kiosk=tv`;

  return (
    <div>
      <PageHeading
        title="Analytics"
        description="Live ticket outcomes alongside model and retrieval diagnostics from BigQuery."
        action={
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-sm"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        }
      />

      {error && (
        <Card className="mb-6 border-[#5c1a26] bg-[#2b0d12] p-4 text-sm text-priority-urgent">{error}</Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <ChartCard title="Ticket outcomes" subtitle={`${data?.total ?? "—"} tickets in this period`}>
          <ResponsiveContainer>
            <PieChart>
              <Pie
                data={outcomeData}
                dataKey="value"
                nameKey="name"
                innerRadius={55}
                outerRadius={90}
                paddingAngle={3}
                stroke="none"
              >
                {outcomeData.map((_, i) => (
                  <Cell key={i} fill={OUTCOME_COLORS[i % OUTCOME_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Volume by priority" subtitle="Across all tickets currently in the inbox">
          <ResponsiveContainer>
            <BarChart data={priorityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f4" vertical={false} />
              <XAxis dataKey="priority" tick={{ fontSize: 12 }} tickLine={false} axisLine={{ stroke: "#e2e8f4" }} />
              <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                {priorityData.map((d, i) => (
                  <Cell key={i} fill={PRIORITY_COLORS[d.priority]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Tickets created each day" subtitle="Hover a point for the exact count">
          <ResponsiveContainer>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#245bdb" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#245bdb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f4" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#e2e8f4" }} />
              <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="total" stroke="#245bdb" strokeWidth={2} fill="url(#vol)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
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
          className="h-[700px] w-full border-0"
          title={`Grafana: ${dashboard}`}
        />
        <p className="border-t border-line px-6 py-3 text-xs text-ink-soft">
          Model and retrieval diagnostics (confidence distributions, latency percentiles, faithfulness/relevance
          trends, retrieval-miss rate) are computed in Grafana straight from the BigQuery fact table, real
          histograms and percentiles that don&apos;t belong in a hand-rolled chart.
        </p>
      </Card>
    </div>
  );
}
