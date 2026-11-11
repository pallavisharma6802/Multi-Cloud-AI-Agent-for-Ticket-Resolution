"use client";
import Link from "next/link";
import {
  ArrowRight,
  Sparkles,
  SearchCheck,
  FileCheck2,
  FileSearch,
  ShieldCheck,
  Repeat,
  Lock,
  SmilePlus,
} from "lucide-react";
import { Card, Button } from "@/components/ui";

const AGENTS = [
  { icon: SearchCheck, title: "Intent & priority", body: "Classifies what the ticket is actually asking for and how urgent it is." },
  { icon: FileSearch, title: "Retrieval", body: "Pulls the knowledge-base passages that are relevant to the request." },
  { icon: FileCheck2, title: "Document grader (CRAG)", body: "Scores each retrieved passage and drops anything that doesn't apply." },
  { icon: Sparkles, title: "Drafting", body: "Writes a response grounded only in the passages that passed grading." },
  { icon: ShieldCheck, title: "Judge (self-RAG)", body: "Checks the draft's faithfulness and relevance, escalating to a human when it can't be sure." },
  { icon: Repeat, title: "Continuation", body: "Decides whether the draft needs another retrieval/drafting pass." },
  { icon: Lock, title: "Security", body: "Screens for sensitive or risky content that shouldn't go out unreviewed." },
  { icon: SmilePlus, title: "Sentiment", body: "Reads tone, so frustrated or urgent requests get flagged accordingly." },
];

export default function HomePage() {
  return (
    <div>
      <section className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <h1 className="animate-wordmark text-6xl font-extrabold tracking-tight text-ink sm:text-7xl">
          resolve
        </h1>
        <span className="animate-underline mt-1 block h-1 w-28 rounded-full bg-brand-gradient" />

        <p className="animate-fade-up mt-6 max-w-xl text-xl font-medium text-ink" style={{ animationDelay: "0.2s" }}>
          AI support for your organization.
        </p>
        <p className="animate-fade-up mt-2 max-w-lg text-sm text-ink-soft" style={{ animationDelay: "0.3s" }}>
          A multi-agent pipeline that triages, researches, drafts, and judges its own answers, escalating
          to a human the moment it isn&apos;t sure.
        </p>

        <div className="animate-fade-up mt-8 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: "0.4s" }}>
          <Link href="/overview">
            <Button>
              Open the dashboard — VS Code demo <ArrowRight size={15} />
            </Button>
          </Link>
          <Link href="/submit">
            <Button variant="secondary">Create a ticket — VS Code demo</Button>
          </Link>
        </div>
      </section>

      <section className="mt-12 mb-6">
        <div className="mx-auto max-w-xl text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">How it works</h2>
          <p className="mt-2 text-sm text-ink-soft">Eight agents, one pipeline, every step logged.</p>
        </div>

        <div className="mx-auto mt-10 flex max-w-xl flex-col">
          {AGENTS.map((a, i) => (
            <div key={a.title} className="flex gap-4">
              <div className="flex flex-col items-center">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                  <a.icon size={16} />
                </span>
                {i < AGENTS.length - 1 && <span className="my-1 w-px flex-1 bg-line" />}
              </div>
              <div className={i < AGENTS.length - 1 ? "pb-8" : ""}>
                <span className="text-xs font-semibold text-ink-faint">Step {i + 1} of {AGENTS.length}</span>
                <div className="text-sm font-semibold text-ink">{a.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-ink-soft">{a.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
