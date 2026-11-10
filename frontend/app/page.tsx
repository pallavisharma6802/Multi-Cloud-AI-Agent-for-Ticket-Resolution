"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Clock,
  Plus,
  ArrowRight,
  RefreshCw,
  Tag,
  Search,
  PenLine,
  ShieldCheck,
  Ticket,
  Sparkles,
  Users,
  ScanSearch,
  FileSearch,
  Gavel,
  Repeat,
  Lock,
  Smile,
} from "lucide-react";
import { getOverview, Overview } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import TicketRow from "@/components/TicketRow";

export default function Home() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

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
    { icon: Tag, title: "Classify", body: "Reads the ticket, assigns category + priority." },
    { icon: Search, title: "Retrieve & grade", tag: "CRAG", body: "Pulls candidate docs, grades each relevant or not, rewrites the search if retrieval missed." },
    { icon: PenLine, title: "Draft & judge", tag: "self-RAG", body: "Drafts an answer, a judge scores faithfulness + relevance, sends it back for a redraft if weak." },
    { icon: ShieldCheck, title: "Resolve or escalate", body: "Confident answers go out. Anything uncertain routes to your team with the full evidence trail." },
  ];

  const agents = [
    { icon: Users, name: "Intent / Priority", role: "Classifies category + urgency" },
    { icon: ScanSearch, name: "Retrieval", role: "Hybrid dense + BM25 search, reciprocal-rank fusion" },
    { icon: FileSearch, name: "Document grader", role: "CRAG — grades relevance, rewrites the query" },
    { icon: PenLine, name: "Drafting", role: "Writes the grounded response" },
    { icon: Gavel, name: "Judge", role: "self-RAG — scores faithfulness + relevance" },
    { icon: Repeat, name: "Continuation", role: "Decides retry / proceed / escalate at each step" },
    { icon: Lock, name: "Security", role: "Screens for prompt injection + unsafe content" },
    { icon: Smile, name: "Sentiment (Azure NLP)", role: "Reads customer tone" },
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

      <Card className="relative mb-6 overflow-hidden p-7">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-brand-gradient opacity-[0.07]" />
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-brand-500" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-brand-500">A multi-agent pipeline, not one prompt</h2>
        </div>
        <p className="mt-2 max-w-3xl text-base text-ink-soft">
          Every ticket runs through a real self-RAG / CRAG loop — eight distinct agents, each with its own
          job, orchestrated by a LangGraph state machine that can retry or escalate at two different points.
        </p>

        <div className="relative mt-7 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="absolute left-0 right-0 top-6 hidden h-px bg-gradient-to-r from-transparent via-line to-transparent lg:block" />
          {steps.map((s, i) => (
            <div key={s.title} className="relative">
              <div className="flex items-center gap-3">
                <span className="relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
                  <s.icon size={20} strokeWidth={2.25} />
                </span>
                <div className="text-3xl font-bold text-line">{i + 1}</div>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="text-base font-bold text-ink">{s.title}</div>
                {s.tag && (
                  <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-bold text-teal-500">{s.tag}</span>
                )}
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{s.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-8 border-t border-line pt-6">
          <h3 className="text-xs font-bold uppercase tracking-widest text-ink-faint">The agent roster</h3>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {agents.map((a) => (
              <div key={a.name} className="flex items-start gap-3 rounded-xl border border-line p-3.5 transition hover:border-brand-500/30 hover:bg-brand-50/40">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-ink-soft">
                  <a.icon size={15} />
                </span>
                <div>
                  <div className="text-sm font-bold text-ink">{a.name}</div>
                  <p className="mt-0.5 text-xs leading-snug text-ink-soft">{a.role}</p>
                </div>
              </div>
            ))}
          </div>
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
        <StatCard icon={Ticket} label="Tickets" value={data?.total ?? "—"} foot={`Created in the last ${days} days`} tone="brand" />
        <StatCard icon={Sparkles} label="AI answered" value={data?.ai_resolved ?? "—"} foot="Generated answer, awaiting confirmation" />
        <StatCard icon={ShieldCheck} label="Needs human review" value={data?.needs_review ?? "—"} foot="Waiting for a reviewer" tone="amber" />
        <StatCard icon={Clock} label="Open" value={data?.open ?? "—"} foot="Not yet processed" tone="teal" />
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
