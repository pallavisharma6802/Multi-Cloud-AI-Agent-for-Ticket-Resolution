"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/Icon";
import TicketTable from "@/components/TicketTable";
import { TicketSummary, listTickets } from "@/lib/api";
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
  const filtered = tickets.filter(
    (t) =>
      (!tab || t.status === tab) &&
      (!priority || t.priority === priority) &&
      `${t.title} ${t.ticket_id} ${t.user_email} ${t.intent}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  function exportCsv() {
    const rows = [
      ["Ticket", "Title", "Requester", "Status", "Priority", "Intent"],
      ...filtered.map((t) => [
        t.ticket_id,
        t.title,
        t.user_email,
        t.status,
        t.priority,
        t.intent || "",
      ]),
    ];
    const csv = rows
      .map((r) =>
        r.map((v) => '"' + String(v).replaceAll('"', '""') + '"').join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "resolve-tickets.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVERY CONVERSATION COUNTS</div>
          <h1>Ticket inbox</h1>
          <p className="subtle">
            Find the signal. Review the evidence. Keep things moving.
          </p>
        </div>
        <Link href="/submit" className="btn btn-primary">
          <Icon name="plus" size={15} />
          Create ticket
        </Link>
      </div>
      <div className="stats-grid">
        {[
          { label: "All tickets", value: tickets.length, icon: "inbox" },
          {
            label: "Needs review",
            value: tickets.filter((t) => t.status === "in_progress").length,
            icon: "clock",
          },
          {
            label: "Resolved",
            value: tickets.filter((t) => t.status === "resolved").length,
            icon: "check",
          },
          {
            label: "High priority",
            value: tickets.filter((t) =>
              ["high", "urgent"].includes(t.priority),
            ).length,
            icon: "bolt",
          },
        ].map((s) => (
          <div className="stat-card" key={s.label}>
            <div className="stat-top">
              {s.label}
              <Icon name={s.icon} size={16} />
            </div>
            <div className="stat-value">
              {loading && !tickets.length ? "—" : s.value}
            </div>
          </div>
        ))}
      </div>
      {error && (
        <div className="error-box">
          {error}
          <button className="btn" onClick={load}>
            Retry
          </button>
        </div>
      )}
      <section className="panel">
        <div className="queue-toolbar">
          <div className="tabs">
            {[
              { v: "", l: "All tickets" },
              { v: "in_progress", l: "Needs review" },
              { v: "resolved", l: "Resolved" },
              { v: "open", l: "Open" },
            ].map((t) => (
              <button
                key={t.v}
                className={`tab ${tab === t.v ? "active" : ""}`}
                onClick={() => setTab(t.v)}
              >
                {t.l}
                <span className="tab-count">
                  {tickets.filter((x) => !t.v || x.status === t.v).length}
                </span>
              </button>
            ))}
          </div>
          <label className="search-field">
            <Icon name="search" size={14} />
            <input
              aria-label="Search tickets"
              placeholder="Search tickets…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        <div className="filters">
          <Icon name="filter" size={13} />
          <select
            aria-label="Filter by priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
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
              className="text-link"
              onClick={() => {
                setSearch("");
                setPriority("");
                setTab("");
              }}
            >
              Clear filters
            </button>
          )}
          <span className="subtle" style={{ marginLeft: "auto", fontSize: 10 }}>
            {filtered.length} tickets
          </span>
          <button
            className="btn"
            onClick={exportCsv}
            disabled={!filtered.length}
          >
            Export CSV
          </button>
          <button className="btn" aria-label="Refresh tickets" onClick={load}>
            <Icon
              name="refresh"
              size={13}
              className={loading ? "spinner" : ""}
            />
          </button>
        </div>
        <TicketTable tickets={filtered} loading={loading} />
      </section>
      <div className="footer-note">
        <span>Showing up to 500 most recent tickets</span>
        <span>Auto-refresh every 30 seconds</span>
      </div>
    </div>
  );
}
