"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Clock, Plus, ArrowRight, RefreshCw, Tag, Search, PenLine, ShieldCheck } from "lucide-react";
import { getOverview, Overview } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import TicketRow from "@/components/TicketRow";

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

  const steps = [
    {
      icon: Tag,
      title: "Classify",
      body: "An intent agent reads the ticket and assigns category + priority.",
    },
    {
      icon: Search,
      title: "Retrieve & grade (CRAG)",
      body: "Pulls candidate docs from your knowledge base, then an LLM grades each one relevant or not and rewrites the search if retrieval missed.",
    },
    {
      icon: PenLine,
      title: "Draft & judge (self-RAG)",
      body: "Drafts a grounded answer, then a judge agent scores faithfulness and relevance and sends it back for a redraft if it's not good enough.",
    },
    {
      icon: ShieldCheck,
      title: "Resolve or escalate",
      body: "Confident, well-grounded answers go out. Anything uncertain is routed to your team with the full evidence trail attached.",
    },
  ];

  return (
    <div>
      <PageHeading
        title="AI support for your organization"
        description="Your knowledge. Helpful answers. Less back-and-forth. Human review stays one click away."
        action={
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={() => setDays(days === 7 ? 30 : 7)}>
              <Clock size={15} /> Last {days} days
            </Button>
            <Link href="/submit">
              <Button>
                <Plus size={15} /> Create ticket
              </Button>
            </Link>
          </div>
        }
      />

      <Card className="mb-8 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">How it works</h2>
        <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <div key={s.title} className="flex gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-500">
                <s.icon size={16} />
              </span>
              <div>
                <div className="text-sm font-semibold text-ink">
                  {i + 1}. {s.title}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-soft">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {error && (
        <Card className="mb-6 border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          We couldn&apos;t refresh the workspace: {error}{" "}
          <button onClick={load} className="font-semibold underline">
            Try again
          </button>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Tickets" value={data?.total ?? "—"} foot={`Created in the last ${days} days`} tone="brand" />
        <StatCard label="AI answered" value={data?.ai_resolved ?? "—"} foot="Generated answer, awaiting confirmation" />
        <StatCard label="Needs human review" value={data?.needs_review ?? "—"} foot="Waiting for a reviewer" tone="amber" />
        <StatCard label="Open" value={data?.open ?? "—"} foot="Not yet processed" tone="teal" />
      </div>

      <Card className="mt-8">
        <div className="flex items-center justify-between border-b border-line px-6 py-5">
          <div>
            <h2 className="text-lg font-semibold text-ink">Recent tickets</h2>
            <p className="text-sm text-ink-soft">Open a ticket to read its answer, sources, and trail.</p>
          </div>
          <Link href="/triage" className="flex items-center gap-1 text-sm font-semibold text-brand-500 hover:text-brand-600">
            View inbox <ArrowRight size={14} />
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
