"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import gsap from "gsap";
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
  { icon: SearchCheck, title: "Intent & priority", body: "Classifies what the ticket is actually asking for and how urgent it is.", bg: "#eaf4fb", fg: "#1f6b93" },
  { icon: FileSearch, title: "Retrieval", body: "Pulls the knowledge-base passages that are relevant to the request.", bg: "#f3effe", fg: "#6d28d9" },
  { icon: FileCheck2, title: "Document grader (CRAG)", body: "Scores each retrieved passage and drops anything that doesn't apply.", bg: "#ecfdf5", fg: "#047857" },
  { icon: Sparkles, title: "Drafting", body: "Writes a response grounded only in the passages that passed grading.", bg: "#fff7ed", fg: "#c2410c" },
  { icon: ShieldCheck, title: "Judge (self-RAG)", body: "Checks the draft's faithfulness and relevance, escalating to a human when it can't be sure.", bg: "#fdf2f8", fg: "#be185d" },
  { icon: Repeat, title: "Continuation", body: "Decides whether the draft needs another retrieval/drafting pass.", bg: "#fefce8", fg: "#a16207" },
  { icon: Lock, title: "Security", body: "Screens for sensitive or risky content that shouldn't go out unreviewed.", bg: "#fef2f2", fg: "#b91c1c" },
  { icon: SmilePlus, title: "Sentiment", body: "Reads tone, so frustrated or urgent requests get flagged accordingly.", bg: "#e0f2fe", fg: "#0369a1" },
];

const WORDMARK = "resolve".split("");

export default function HomePage() {
  const letterRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const underlineRef = useRef<HTMLSpanElement>(null);
  const taglineRef = useRef<HTMLParagraphElement>(null);
  const subRef = useRef<HTMLParagraphElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
    tl.fromTo(
      letterRefs.current,
      { y: 40, opacity: 0, rotate: 6 },
      { y: 0, opacity: 1, rotate: 0, duration: 0.6, stagger: 0.05 }
    )
      .fromTo(underlineRef.current, { scaleX: 0 }, { scaleX: 1, duration: 0.5, transformOrigin: "left" }, "-=0.2")
      .fromTo(taglineRef.current, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 }, "-=0.2")
      .fromTo(subRef.current, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 }, "-=0.25")
      .fromTo(ctaRef.current, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4 }, "-=0.25");
  }, []);

  return (
    <div>
      <section className="flex flex-col items-center justify-center py-10 text-center">
        <h1 className="flex text-6xl font-extrabold tracking-tight text-ink sm:text-7xl">
          {WORDMARK.map((letter, i) => (
            <span key={i} ref={(el) => void (letterRefs.current[i] = el)} className="inline-block">
              {letter}
            </span>
          ))}
        </h1>
        <span ref={underlineRef} className="mt-1 block h-1 w-28 rounded-full bg-brand-gradient" />

        <p ref={taglineRef} className="mt-6 max-w-xl text-xl font-medium text-ink">
          AI support for your organization.
        </p>
        <p ref={subRef} className="mt-2 max-w-lg text-sm text-ink-soft">
          A multi-agent pipeline that triages, researches, drafts, and judges its own answers, escalating
          to a human the moment it isn&apos;t sure.
        </p>

        <div ref={ctaRef} className="mt-8 flex flex-wrap items-center justify-center gap-3">
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

      <section className="mt-2 mb-6">
        <div className="mx-auto max-w-xl text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">How it works</h2>
          <p className="mt-2 text-sm text-ink-soft">Eight agents, one pipeline, every step logged.</p>
        </div>

        <div className="mx-auto mt-10 flex max-w-xl flex-col">
          {AGENTS.map((a, i) => (
            <div key={a.title} className="flex gap-4">
              <div className="flex flex-col items-center">
                <span
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
                  style={{ background: a.bg, color: a.fg }}
                >
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
