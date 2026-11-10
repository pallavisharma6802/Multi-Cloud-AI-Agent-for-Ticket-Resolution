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
  BookOpen,
} from "lucide-react";
import { getOverview, Overview } from "@/lib/api";
import { Card, PageHeading, StatCard, Button } from "@/components/ui";
import LighthouseHero from "@/components/LighthouseHero";

type Tab = "roster" | "activity" | "explore";

export default function Home() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [tab, setTab] = useState<Tab>("roster");

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
    { icon: FileSearch, name: "Document grader", role: "CRAG, grades relevance and rewrites the query" },
    { icon: PenLine, name: "Drafting", role: "Writes the grounded response" },
    { icon: Gavel, name: "Judge", role: "self-RAG, scores faithfulness and relevance" },
    { icon: Repeat, name: "Continuation", role: "Decides retry / proceed / escalate at each step" },
    { icon: Lock, name: "Security", role: "Screens for prompt injection + unsafe content" },
    { icon: Smile, name: "Sentiment (Azure NLP)", role: "Reads customer tone" },
  ];

  return (
    <div>
      <div className="relative mb-6 overflow-hidden rounded-2xl border border-line">
        <div className="absolute inset-0">
          <LighthouseHero height={260} />
        </div>
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-canvas via-canvas/70 to-canvas/10" />
        <div className="relative px-7 py-8">
          <PageHeading
            title="AI support for your organization"
            description={
              <>
                This build is scoped to a single example: VS Code support, grounded in Microsoft&apos;s own
                public documentation. <span className="text-[#ff7a52]">Not a generic bot</span>, and not
                connected to any real organization&apos;s data.{" "}
                <Link href="/knowledge" className="pointer-events-auto font-semibold text-brand-500 hover:text-brand-600">
                  See what it actually knows <ArrowRight size={12} className="inline" />
                </Link>
              </>
            }
            action={
              <Link href="/submit" className="pointer-events-auto">
                <Button>
                  <Plus size={15} /> Create ticket
                </Button>
              </Link>
            }
          />
          <p className="text-xs font-semibold uppercase tracking-widest text-[#ff7a52]">A beam that only lights what&apos;s really there</p>
        </div>
      </div>

      <Card className="relative mb-6 overflow-hidden p-7">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-brand-gradient opacity-[0.07]" />
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-brand-500" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-brand-500">A multi-agent pipeline, not one prompt</h2>
        </div>
        <p className="mt-2 max-w-3xl text-base text-ink-soft">
          Every ticket runs through a real self-RAG/CRAG loop: eight distinct agents, each with its own
          job, orchestrated by a LangGraph state machine that can retry or escalate at two different points.
        </p>

        <div className="relative mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <div className="absolute left-0 right-0 top-4 hidden h-px bg-gradient-to-r from-transparent via-line to-transparent lg:block" />
          {steps.map((s) => (
            <div key={s.title} className="relative">
              <span className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white">
                <s.icon size={14} strokeWidth={2.25} />
              </span>
              <div className="mt-2.5 flex items-center gap-2">
                <div className="text-sm font-bold text-ink">{s.title}</div>
                {s.tag && (
                  <span className="rounded-full bg-[#3a1710] px-1.5 py-0.5 text-[10px] font-bold text-[#ff7a52]">{s.tag}</span>
                )}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink-soft">{s.body}</p>
            </div>
          ))}
        </div>

      </Card>

      {error && (
        <Card className="mb-6 border-[#5c1a26] bg-[#2b0d12] p-4 text-sm text-priority-urgent">
          Couldn&apos;t refresh the workspace: {error}{" "}
          <button onClick={load} className="font-semibold underline">
            Try again
          </button>
        </Card>
      )}

      <Card>
        <div className="flex items-center justify-between border-b border-line px-2 pt-2">
          <div className="flex gap-1">
            {(
              [
                ["roster", "Agent roster"],
                ["activity", "Activity"],
                ["explore", "Explore"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`rounded-t-lg px-4 py-2.5 text-sm font-semibold transition ${
                  tab === key ? "bg-surface text-ink border-x border-t border-line -mb-px" : "text-ink-faint hover:text-ink-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "activity" && (
            <Button variant="ghost" onClick={() => setDays(days === 7 ? 30 : 7)} className="text-xs">
              <Clock size={13} /> Last {days} days
            </Button>
          )}
        </div>

        <div className="p-6">
          {tab === "roster" && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {agents.map((a) => (
                <div key={a.name} className="flex items-start gap-3 rounded-xl border border-line p-3.5 transition hover:border-brand-500/30 hover:bg-brand-50/40">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-line/60 text-ink-soft">
                    <a.icon size={15} />
                  </span>
                  <div>
                    <div className="text-sm font-bold text-ink">{a.name}</div>
                    <p className="mt-0.5 text-xs leading-snug text-ink-soft">{a.role}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "activity" && (
            <div>
              <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-ink-faint">
                Demo activity, not live production traffic
              </p>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatCard icon={Ticket} label="Tickets" value={data?.total ?? "none yet"} foot={`Created in the last ${days} days`} tone="brand" />
                <StatCard icon={Sparkles} label="AI answered" value={data?.ai_resolved ?? "none yet"} foot="Generated answer, awaiting confirmation" />
                <StatCard icon={ShieldCheck} label="Needs human review" value={data?.needs_review ?? "none yet"} foot="Waiting for a reviewer" tone="amber" />
                <StatCard icon={Clock} label="Open" value={data?.open ?? "none yet"} foot="Not yet processed" tone="teal" />
              </div>
            </div>
          )}

          {tab === "explore" && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Link href="/triage" className="group rounded-2xl border border-line bg-surface p-5 transition hover:border-brand-500/30">
                <div className="flex items-center gap-2 text-ink">
                  <Ticket size={16} className="text-brand-500" />
                  <span className="font-semibold">Inbox</span>
                </div>
                <p className="mt-2 text-sm text-ink-soft">Every ticket, its AI answer, and the evidence trail behind it.</p>
                <span className="mt-3 flex items-center gap-1 text-sm font-semibold text-brand-500 group-hover:text-brand-600">
                  Open the inbox <ArrowRight size={13} />
                </span>
              </Link>
              <Link href="/analytics" className="group rounded-2xl border border-line bg-surface p-5 transition hover:border-brand-500/30">
                <div className="flex items-center gap-2 text-ink">
                  <Sparkles size={16} className="text-teal-500" />
                  <span className="font-semibold">Analytics</span>
                </div>
                <p className="mt-2 text-sm text-ink-soft">Volume, priority mix, and RAG/judge health over time.</p>
                <span className="mt-3 flex items-center gap-1 text-sm font-semibold text-brand-500 group-hover:text-brand-600">
                  View dashboards <ArrowRight size={13} />
                </span>
              </Link>
              <Link href="/knowledge" className="group rounded-2xl border border-line bg-surface p-5 transition hover:border-brand-500/30">
                <div className="flex items-center gap-2 text-ink">
                  <BookOpen size={16} className="text-priority-medium" />
                  <span className="font-semibold">Knowledge base</span>
                </div>
                <p className="mt-2 text-sm text-ink-soft">The 6,347 real VS Code doc chunks this agent actually retrieves from.</p>
                <span className="mt-3 flex items-center gap-1 text-sm font-semibold text-brand-500 group-hover:text-brand-600">
                  See what it knows <ArrowRight size={13} />
                </span>
              </Link>
            </div>
          )}
        </div>
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
