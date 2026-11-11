"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Clock } from "lucide-react";
import { TicketSummary, listTickets } from "@/lib/api";
import { Card, PageHeading, Button, PriorityBadge } from "@/components/ui";

const COLUMNS: Array<{ key: string; label: string; accent: string }> = [
  { key: "open", label: "Ticket opened", accent: "#e3a655" },
  { key: "urgent", label: "Urgent", accent: "#f87171" },
  { key: "in_progress", label: "On hold · needs review", accent: "#f2b84b" },
];

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function ReviewCard({ ticket }: { ticket: TicketSummary }) {
  return (
    <Link
      href={`/tickets/${ticket.ticket_id}`}
      className="block rounded-xl border border-line bg-surface p-4 shadow-card transition hover:border-brand-500/40 hover:shadow-glow"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="line-clamp-2 text-sm font-semibold text-ink">{ticket.title}</span>
        {ticket.priority && <PriorityBadge priority={ticket.priority} />}
      </div>
      <p className="mt-1.5 line-clamp-2 text-xs text-ink-soft">{ticket.description}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-ink-faint">
        <span className="truncate">{ticket.user_email}</span>
        <span className="flex items-center gap-1 shrink-0">
          <Clock size={12} /> {timeAgo(ticket.created_at)}
        </span>
      </div>
      {ticket.intent && (
        <span className="mt-2 inline-flex items-center rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700">
          {ticket.intent}
        </span>
      )}
    </Link>
  );
}

export default function ReviewBoard() {
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
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

  const grouped = useMemo(() => {
    const map: Record<string, TicketSummary[]> = { open: [], urgent: [], in_progress: [] };
    tickets.forEach((t) => {
      const status = (t.status || "").toLowerCase();
      const priority = (t.priority || "").toLowerCase();
      if (status === "resolved" || status === "closed") return;
      if (priority === "urgent") map.urgent.push(t);
      else if (status === "in_progress") map.in_progress.push(t);
      else map.open.push(t);
    });
    return map;
  }, [tickets]);

  return (
    <div>
      <PageHeading
        title="Review board"
        description="Tickets grouped by where they stand, for a fast human-review pass."
        action={
          <Button variant="secondary" onClick={load}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        }
      />

      {error && (
        <Card className="mb-6 border-priority-urgent/30 bg-priority-urgent/10 p-4 text-sm text-priority-urgent">{error}</Card>
      )}

      {loading && !tickets.length ? (
        <div className="py-14 text-center text-sm text-ink-soft">Loading board…</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {COLUMNS.map((col) => {
            const items = grouped[col.key] || [];
            return (
              <div key={col.key} className="flex flex-col rounded-2xl border border-line bg-canvas/60 p-3">
                <div className="mb-3 flex items-center justify-between px-1">
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <span className="h-2 w-2 rounded-full" style={{ background: col.accent }} />
                    {col.label}
                  </span>
                  <span className="rounded-full bg-line/70 px-2 py-0.5 text-xs font-semibold text-ink-soft">
                    {items.length}
                  </span>
                </div>
                <div className="flex flex-col gap-2.5">
                  {items.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-xs text-ink-faint">
                      Nothing here
                    </div>
                  ) : (
                    items.map((t) => <ReviewCard key={t.ticket_id} ticket={t} />)
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
