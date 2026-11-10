"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Plus, RefreshCw, Ticket, Sparkles, ShieldCheck, CheckCircle2, ArrowRight } from "lucide-react";
import { getOverview, Overview } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import TicketRow from "@/components/TicketRow";

const OUTCOME_COLORS = ["#329dd2", "#8b5cf6", "#f5b942", "#3d4f66"];
const CHART_LINE = "#1b2840";
const CHART_TICK = { fill: "#9fb0c6", fontSize: 12 };
const CHART_TOOLTIP_STYLE = {
  background: "#0e1726",
  border: "1px solid #1b2840",
  borderRadius: 10,
  color: "#f2f5fa",
  fontSize: 13,
};

export default function Home() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [days] = useState(30);

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

  const outcomeData = [
    { name: "AI answered", value: data?.ai_resolved || 0 },
    { name: "Human resolved", value: data?.human_resolved || 0 },
    { name: "Needs review", value: data?.needs_review || 0 },
    { name: "Open", value: data?.open || 0 },
  ];
  const trendData = (data?.daily || []).map((d) => ({ date: d.date.slice(5), total: d.total, resolved: d.resolved }));

  return (
    <div>
      <PageHeading
        title="Support overview"
        description="Live ticket volume and outcomes for the VS Code support workspace."
        action={
          <Link href="/submit">
            <Button>
              <Plus size={15} /> New ticket
            </Button>
          </Link>
        }
      />

      {error && (
        <Card className="mb-6 border-[#5c1a26] bg-[#2b0d12] p-4 text-sm text-priority-urgent">
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
                    <stop offset="0%" stopColor="#329dd2" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#329dd2" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_LINE} vertical={false} />
                <XAxis dataKey="date" tick={{ ...CHART_TICK, fontSize: 11 }} tickLine={false} axisLine={{ stroke: CHART_LINE }} />
                <YAxis tick={CHART_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={{ color: "#9fb0c6" }} />
                <Area type="monotone" dataKey="total" stroke="#4db2e3" strokeWidth={2} fill="url(#vol)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-sm font-semibold text-ink">Ticket outcomes</h3>
          <p className="text-xs text-ink-soft">{data?.total ?? 0} tickets in this period</p>
          <div className="mt-2 h-64 w-full">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={outcomeData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={3} stroke="none">
                  {outcomeData.map((_, i) => (
                    <Cell key={i} fill={OUTCOME_COLORS[i % OUTCOME_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelStyle={{ color: "#9fb0c6" }} />
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
