"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { TicketSummary, listTickets } from "@/lib/api";

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700",
  high: "bg-orange-100 text-orange-700",
  urgent: "bg-red-100 text-red-700",
};

export default function TriagePage() {
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [domainFilter, setDomainFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    listTickets({
      status_filter: statusFilter || undefined,
      priority_filter: priorityFilter || undefined,
      domain_pack_filter: domainFilter || undefined,
      limit: 100,
    })
      .then(setTickets)
      .catch((e) => setError(`Could not load tickets -- is the backend running? (${e.message})`))
      .finally(() => setLoading(false));
  }

  useEffect(load, [statusFilter, priorityFilter, domainFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Triage Queue</h1>
        <button
          onClick={load}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
        >
          Refresh
        </button>
      </div>

      <div className="flex gap-4">
        <FilterSelect
          label="Status"
          value={statusFilter}
          onChange={setStatusFilter}
          options={["open", "in_progress", "resolved", "closed"]}
        />
        <FilterSelect
          label="Priority"
          value={priorityFilter}
          onChange={setPriorityFilter}
          options={["low", "medium", "high", "urgent"]}
        />
        <FilterSelect
          label="Domain Pack"
          value={domainFilter}
          onChange={setDomainFilter}
          options={["it_saas", "healthcare"]}
        />
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Ticket</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Domain</th>
              <th className="px-4 py-3">Intent</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!loading && tickets.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                  No tickets found.
                </td>
              </tr>
            )}
            {tickets.map((t) => (
              <tr key={t.ticket_id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  <Link href={`/tickets/${t.ticket_id}`} className="text-indigo-600 hover:underline">
                    {t.ticket_id}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-900">{t.title}</td>
                <td className="px-4 py-3 text-slate-600">{t.domain_pack ?? "-"}</td>
                <td className="px-4 py-3 text-slate-600">{t.intent ?? "-"}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PRIORITY_STYLES[t.priority] ?? "bg-slate-100 text-slate-700"}`}>
                    {t.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{t.status}</td>
                <td className="px-4 py-3 text-slate-500">{new Date(t.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 rounded-md border border-slate-300 px-2 py-1 text-sm"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
