"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  Sparkles,
  SearchCheck,
  FileCheck2,
  ShieldCheck,
  UserCheck,
  Gauge,
  Ticket,
  CheckCircle2,
} from "lucide-react";
import { getOverview, Overview } from "@/lib/api";
import { Card, Button } from "@/components/ui";

const STEPS = [
  {
    icon: SearchCheck,
    title: "Understand the ticket",
    body: "Intent, priority, and sentiment are classified before anything else runs, so routing decisions start from a real read of the request.",
  },
  {
    icon: FileCheck2,
    title: "Retrieve and grade evidence",
    body: "Relevant knowledge-base docs are pulled and graded for relevance (CRAG) so a draft is only built on evidence that actually applies.",
  },
  {
    icon: Sparkles,
    title: "Draft a response",
    body: "A grounded draft is written from the graded evidence, not from the model's own memory of how things usually work.",
  },
  {
    icon: ShieldCheck,
    title: "Judge it before it ships",
    body: "A self-RAG judge checks faithfulness and relevance against the evidence, and flags anything it can't fully support.",
  },
  {
    icon: UserCheck,
    title: "Escalate when it should",
    body: "Low-confidence or sensitive cases route to a human reviewer instead of going out the door unchecked.",
  },
];

export default function HomePage() {
  const [data, setData] = useState<Overview | null>(null);

  useEffect(() => {
    getOverview(30).then(setData).catch(() => {});
  }, []);

  return (
    <div>
      <section className="flex min-h-[70vh] flex-col items-center justify-center text-center">
        <span className="animate-fade-up inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-semibold text-brand-700 shadow-card">
          <Sparkles size={13} /> Example build · VS Code support
        </span>

        <h1 className="animate-wordmark mt-6 text-6xl font-extrabold tracking-tight text-ink sm:text-7xl">
          resolve
        </h1>
        <span className="animate-underline mt-1 block h-1 w-28 rounded-full bg-brand-gradient" />

        <p className="animate-fade-up mt-6 max-w-xl text-xl font-medium text-ink" style={{ animationDelay: "0.2s" }}>
          AI support for your organization.
        </p>
        <p className="animate-fade-up mt-2 max-w-lg text-sm text-ink-soft" style={{ animationDelay: "0.3s" }}>
          A multi-agent pipeline that triages, researches, drafts, and judges its own answers to VS Code
          support tickets, escalating to a human the moment it isn&apos;t sure.
        </p>

        <div className="animate-fade-up mt-8 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: "0.4s" }}>
          <Link href="/overview">
            <Button>
              Open the dashboard <ArrowRight size={15} />
            </Button>
          </Link>
          <Link href="/submit">
            <Button variant="secondary">Try submitting a ticket</Button>
          </Link>
        </div>

        <a href="#how-it-works" className="animate-fade-up mt-16 flex flex-col items-center gap-1 text-xs font-semibold text-ink-faint" style={{ animationDelay: "0.6s" }}>
          Scroll to see how it works
          <ChevronDown size={18} className="animate-scroll-cue" />
        </a>
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="p-5 text-center">
          <Ticket className="mx-auto text-brand-500" size={20} />
          <div className="mt-2 text-2xl font-bold text-ink">{data?.total ?? "—"}</div>
          <div className="text-xs text-ink-soft">Tickets handled (30d)</div>
        </Card>
        <Card className="p-5 text-center">
          <Gauge className="mx-auto text-[#8b5cf6]" size={20} />
          <div className="mt-2 text-2xl font-bold text-ink">{data?.ai_resolved ?? "—"}</div>
          <div className="text-xs text-ink-soft">Answered by AI</div>
        </Card>
        <Card className="p-5 text-center">
          <ShieldCheck className="mx-auto text-priority-medium" size={20} />
          <div className="mt-2 text-2xl font-bold text-ink">{data?.needs_review ?? "—"}</div>
          <div className="text-xs text-ink-soft">Escalated to a human</div>
        </Card>
        <Card className="p-5 text-center">
          <CheckCircle2 className="mx-auto text-[#22c55e]" size={20} />
          <div className="mt-2 text-2xl font-bold text-ink">{data?.resolved ?? "—"}</div>
          <div className="text-xs text-ink-soft">Fully resolved</div>
        </Card>
      </section>

      <section id="how-it-works" className="mt-20 scroll-mt-8">
        <div className="mx-auto max-w-xl text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">How it works</h2>
          <p className="mt-2 text-sm text-ink-soft">
            Every ticket moves through the same five-step pipeline, end to end, with every step logged.
          </p>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((s, i) => (
            <Card key={s.title} className="flex flex-col gap-3 p-5">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  <s.icon size={16} />
                </span>
                <span className="text-xs font-semibold text-ink-faint">Step {i + 1}</span>
              </div>
              <div className="text-sm font-semibold text-ink">{s.title}</div>
              <p className="text-xs leading-relaxed text-ink-soft">{s.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-16 mb-4">
        <Card className="flex flex-col items-center gap-4 p-10 text-center">
          <h3 className="text-xl font-semibold text-ink">See it running on real tickets</h3>
          <p className="max-w-md text-sm text-ink-soft">
            The dashboard shows live outcomes and diagnostics; the inbox and review board show exactly
            what a human reviewer sees for the cases the AI didn&apos;t resolve on its own.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link href="/overview">
              <Button>
                Open the dashboard <ArrowRight size={15} />
              </Button>
            </Link>
            <Link href="/review">
              <Button variant="secondary">See the review board</Button>
            </Link>
          </div>
        </Card>
      </section>
    </div>
  );
}
