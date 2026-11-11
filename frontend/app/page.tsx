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
  { icon: SearchCheck, title: "Intent & priority", body: "Classifies what the ticket is actually asking for and how urgent it is." },
  { icon: FileSearch, title: "Retrieval", body: "Pulls the knowledge-base passages that are relevant to the request." },
  { icon: FileCheck2, title: "Document grader (CRAG)", body: "Scores each retrieved passage and drops anything that doesn't apply." },
  { icon: Sparkles, title: "Drafting", body: "Writes a response grounded only in the passages that passed grading." },
  { icon: ShieldCheck, title: "Judge (self-RAG)", body: "Checks the draft's faithfulness and relevance, escalating to a human when it can't be sure." },
  { icon: Repeat, title: "Continuation", body: "Decides whether the draft needs another retrieval/drafting pass." },
  { icon: Lock, title: "Security", body: "Screens for sensitive or risky content that shouldn't go out unreviewed." },
  { icon: SmilePlus, title: "Sentiment", body: "Reads tone, so frustrated or urgent requests get flagged accordingly." },
];

const WORDMARK = "resolve".split("");

export default function HomePage() {
  const letterRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const underlineRef = useRef<HTMLSpanElement>(null);
  const taglineRef = useRef<HTMLParagraphElement>(null);
  const subRef = useRef<HTMLParagraphElement>(null);
  const ctaRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLDivElement | null)[]>([]);
  const iconRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const lineRefs = useRef<(HTMLSpanElement | null)[]>([]);

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

  useEffect(() => {
    // Scroll-reveal the pipeline timeline: each step's icon pops in and its
    // body slides up as it enters view; the connecting line underneath it
    // fills in right after, so the "path" visibly draws itself downward.
    gsap.set(stepRefs.current, { opacity: 0, y: 24 });
    gsap.set(iconRefs.current, { scale: 0.5, opacity: 0 });
    gsap.set(lineRefs.current, { scaleY: 0 });

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const i = Number((entry.target as HTMLElement).dataset.index);
          observer.unobserve(entry.target);
          const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
          tl.to(iconRefs.current[i], { scale: 1, opacity: 1, duration: 0.4 })
            .to(stepRefs.current[i], { opacity: 1, y: 0, duration: 0.45 }, "-=0.3")
            .to(lineRefs.current[i], { scaleY: 1, duration: 0.4, transformOrigin: "top" }, "-=0.1");
        });
      },
      { threshold: 0.4, rootMargin: "0px 0px -10% 0px" }
    );

    stepRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div>
      <section className="flex flex-col items-center justify-center py-10 text-center">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-ink-soft">
          <Sparkles size={11} /> Example build
        </span>

        <h1 className="mt-5 flex text-5xl font-semibold tracking-tight text-ink sm:text-6xl">
          {WORDMARK.map((letter, i) => (
            <span key={i} ref={(el) => void (letterRefs.current[i] = el)} className="inline-block">
              {letter}
            </span>
          ))}
        </h1>
        <span ref={underlineRef} className="mt-2 block h-0.5 w-20 rounded-full bg-brand-500" />

        <p ref={taglineRef} className="mt-6 max-w-xl text-lg font-medium text-ink">
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
          <h2 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">How it works</h2>
          <p className="mt-2 text-sm text-ink-soft">Eight agents, one pipeline, every step logged.</p>
        </div>

        <div className="mx-auto mt-10 flex max-w-xl flex-col">
          {AGENTS.map((a, i) => (
            <div
              key={a.title}
              data-index={i}
              ref={(el) => void (stepRefs.current[i] = el)}
              className="flex gap-4"
            >
              <div className="flex flex-col items-center">
                <span
                  ref={(el) => void (iconRefs.current[i] = el)}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700"
                >
                  <a.icon size={15} />
                </span>
                {i < AGENTS.length - 1 && (
                  <span
                    ref={(el) => void (lineRefs.current[i] = el)}
                    className="my-1 w-px flex-1 bg-line"
                  />
                )}
              </div>
              <div className={i < AGENTS.length - 1 ? "pb-8" : ""}>
                <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint">Step {i + 1} of {AGENTS.length}</span>
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
