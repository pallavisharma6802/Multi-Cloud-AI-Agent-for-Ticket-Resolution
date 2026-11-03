"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Sparkles, Send, ArrowRight, Loader2 } from "lucide-react";
import {
  DomainPack,
  TicketResolutionResponse,
  getDomainPacks,
  submitTicket,
} from "@/lib/api";
import { Card, Button } from "@/components/ui";

const PROMPTS = [
  "I can't access my account — forgot my password and can't sign in.",
  "I was charged twice for the same subscription this month.",
  "The integrated terminal won't open in VS Code on macOS.",
];

type Msg = {
  role: "agent" | "user";
  text: string;
  result?: TicketResolutionResponse;
};

export default function Submit() {
  const [packs, setPacks] = useState<DomainPack[]>([]);
  const [pack, setPack] = useState("");
  const [email, setEmail] = useState("");
  const [stage, setStage] = useState<"email" | "issue" | "done">("email");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([
    { role: "agent", text: "Hi! I'm here to help. What's the best email to reach you at?" },
  ]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getDomainPacks()
      .then((d) => {
        setPacks(d.packs);
        setPack(d.default);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(text: string) {
    const value = text.trim();
    if (!value || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: value }]);

    if (stage === "email") {
      setEmail(value);
      setStage("issue");
      setMessages((m) => [
        ...m,
        { role: "agent", text: "Thanks. Now tell me what's going on — include any error messages and what you've already tried." },
      ]);
      return;
    }

    // stage === "issue": submit to the real agent pipeline
    setLoading(true);
    try {
      const res = await submitTicket({
        title: value.slice(0, 80),
        description: value,
        user_email: email,
        domain_pack: pack,
      });
      setStage("done");
      setMessages((m) => [
        ...m,
        {
          role: "agent",
          text:
            res.drafted_response ||
            "This needs a support specialist — I've routed it for human review with my notes attached.",
          result: res,
        },
      ]);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "agent", text: `Something went wrong: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-10rem)] max-w-3xl flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">New ticket</h1>
          <p className="text-sm text-ink-soft">Describe the issue in your own words — an agent will take it from here.</p>
        </div>
        {packs.length > 1 && (
          <select
            value={pack}
            onChange={(e) => setPack(e.target.value)}
            className="rounded-xl border border-line bg-surface px-3 py-2 text-sm"
          >
            {packs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        )}
      </div>

      <Card className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`flex max-w-[80%] gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                {m.role === "agent" && (
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500 text-white">
                    <Sparkles size={15} />
                  </span>
                )}
                <div>
                  <div
                    className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      m.role === "user"
                        ? "bg-brand-500 text-white"
                        : "border border-line bg-slate-50 text-ink"
                    }`}
                  >
                    {m.text}
                  </div>
                  {m.result && (
                    <div className="mt-2 flex items-center gap-3 px-1 text-xs text-ink-soft">
                      <span className="font-medium">
                        {Math.round(m.result.confidence_score * 100)}% confidence
                      </span>
                      <span>·</span>
                      <span>{m.result.processing_time_seconds.toFixed(1)}s</span>
                      <Link
                        href={`/tickets/${m.result.ticket_id}`}
                        className="ml-auto flex items-center gap-1 font-semibold text-brand-500 hover:text-brand-600"
                      >
                        View full ticket <ArrowRight size={13} />
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start gap-3">
              <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500 text-white">
                <Sparkles size={15} />
              </span>
              <div className="flex items-center gap-2 rounded-2xl border border-line bg-slate-50 px-4 py-3 text-sm text-ink-soft">
                <Loader2 size={14} className="animate-spin" />
                Classifying, checking sources, drafting a response…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {stage !== "done" && messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 border-t border-line px-6 py-3">
            {PROMPTS.map((p) => (
              <button
                key={p}
                onClick={() => handleSend(stage === "email" ? "demo@example.com" : p)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-ink-soft transition hover:border-brand-500/40 hover:text-ink"
              >
                {p.length > 50 ? p.slice(0, 50) + "…" : p}
              </button>
            ))}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(input);
          }}
          className="flex items-center gap-3 border-t border-line px-4 py-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading || stage === "done"}
            placeholder={
              stage === "done" ? "Ticket submitted — start a new one below" : stage === "email" ? "you@company.com" : "Type your message…"
            }
            className="flex-1 rounded-xl border border-line bg-slate-50 px-4 py-2.5 text-sm outline-none focus:border-brand-500/50 disabled:opacity-60"
          />
          <Button disabled={loading || stage === "done" || !input.trim()} className="px-3.5">
            <Send size={16} />
          </Button>
        </form>
      </Card>

      {stage === "done" && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="secondary"
            onClick={() => {
              setMessages([{ role: "agent", text: "Hi again! What's the best email to reach you at?" }]);
              setStage("email");
              setEmail("");
            }}
          >
            Start a new ticket
          </Button>
        </div>
      )}
    </div>
  );
}
