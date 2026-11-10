"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Inbox as InboxIcon, Search, Download, RefreshCw, Filter } from "lucide-react";
import { TicketSummary, listTickets } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import TicketRow from "@/components/TicketRow";

const TABS = [
  { v: "", l: "All" },
  { v: "in_progress", l: "Needs review" },
  { v: "resolved", l: "Resolved" },
  { v: "open", l: "Open" },
];

export default function Inbox() {
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [tab, setTab] = useState("");
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    listTickets({ limit: 500 })
      .then((t) => {
        setTickets(t);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  const filtered = useMemo(
    () =>
      tickets.filter(
        (t) =>
          (!tab || t.status === tab) &&
          (!priority || t.priority === priority) &&
          `${t.title} ${t.ticket_id} ${t.user_email} ${t.intent}`.toLowerCase().includes(search.toLowerCase())
      ),
    [tickets, tab, priority, search]
  );

  function exportCsv() {
    const rows = [
      ["Ticket", "Title", "Requester", "Status", "Priority", "Intent"],
      ...filtered.map((t) => [t.ticket_id, t.title, t.user_email, t.status, t.priority, t.intent || ""]),
    ];
    const csv = rows.map((r) => r.map((v) => '"' + String(v).replaceAll('"', '""') + '"').join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "resolve-tickets.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <PageHeading
        title="Inbox"
        description="Find the signal. Review the evidence. Keep things moving."
        action={
          <Link href="/submit">
            <Button>Create ticket</Button>
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="All tickets" value={tickets.length} tone="brand" />
        <StatCard label="Needs review" value={tickets.filter((t) => t.status === "in_progress").length} tone="amber" />
        <StatCard label="Resolved" value={tickets.filter((t) => t.status === "resolved").length} tone="teal" />
        <StatCard label="High priority" value={tickets.filter((t) => ["high", "urgent"].includes(t.priority)).length} />
      </div>

      {error && (
        <Card className="mt-6 border-[#5c1a26] bg-[#2b0d12] p-4 text-sm text-priority-urgent">
          {error}{" "}
          <button className="font-semibold underline" onClick={load}>
            Retry
          </button>
        </Card>
      )}

      <Card className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-5 py-4">
          <div className="flex gap-1 rounded-xl bg-line/60 p-1">
            {TABS.map((t) => (
              <button
                key={t.v}
                onClick={() => setTab(t.v)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  tab === t.v ? "bg-surface text-ink shadow-card" : "text-ink-soft hover:text-ink"
                }`}
              >
                {t.l}
                <span className="ml-1.5 text-xs text-ink-faint">
                  {tickets.filter((x) => !t.v || x.status === t.v).length}
                </span>
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm text-ink-soft">
            <Search size={15} />
            <input
              aria-label="Search tickets"
              placeholder="Search tickets…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 bg-transparent outline-none placeholder:text-ink-faint"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <Filter size={14} className="text-ink-faint" />
          <select
            aria-label="Filter by priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">All priorities</option>
            {["urgent", "high", "medium", "low"].map((p) => (
              <option key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </select>
          {(search || priority || tab) && (
            <button
              className="text-sm font-semibold text-brand-500 hover:text-brand-600"
              onClick={() => {
                setSearch("");
                setPriority("");
                setTab("");
              }}
            >
              Clear filters
            </button>
          )}
          <span className="ml-auto text-xs text-ink-faint">{filtered.length} tickets</span>
          <Button variant="secondary" onClick={exportCsv} disabled={!filtered.length} className="py-1.5">
            <Download size={14} /> Export
          </Button>
          <Button variant="secondary" onClick={load} aria-label="Refresh" className="py-1.5">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </Button>
        </div>

        {loading && !tickets.length ? (
          <div className="px-6 py-14 text-center text-sm text-ink-soft">Loading tickets…</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-14 text-center text-sm text-ink-soft">
            <InboxIcon size={28} className="text-ink-faint" />
            No tickets match these filters.
          </div>
        ) : (
          <div>
            {filtered.map((t) => (
              <TicketRow key={t.ticket_id} ticket={t} />
            ))}
          </div>
        )}
      </Card>

      <div className="mt-4 flex items-center justify-between text-xs text-ink-faint">
        <span>Showing up to 500 most recent tickets</span>
        <span>Auto-refresh every 30 seconds</span>
      </div>
    </div>
  );
}
