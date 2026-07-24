"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { DomainPack, TicketResolutionResponse, getDomainPacks, submitTicket } from "@/lib/api";

export default function SubmitPage() {
  const [packs, setPacks] = useState<DomainPack[]>([]);
  const [domainPack, setDomainPack] = useState<string>("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TicketResolutionResponse | null>(null);

  useEffect(() => {
    getDomainPacks()
      .then((data) => {
        setPacks(data.packs);
        setDomainPack(data.default);
      })
      .catch((e) => setError(`Could not load domain packs -- is the backend running? (${e.message})`));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await submitTicket({
        title,
        description,
        user_email: userEmail,
        domain_pack: domainPack || undefined,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Ticket submission failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Submit a Ticket</h1>
        <p className="mt-1 text-sm text-slate-600">
          This calls the live pipeline synchronously -- expect anywhere from a few seconds to
          {" "}
          {"~"}30s depending on how many CRAG/Reflexion loop iterations the Continuation Agent decides
          are needed.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
        <div>
          <label className="block text-sm font-medium text-slate-700">Domain Pack</label>
          <select
            value={domainPack}
            onChange={(e) => setDomainPack(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {packs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
          {packs.find((p) => p.id === domainPack) && (
            <p className="mt-1 text-xs text-slate-500">
              {packs.find((p) => p.id === domainPack)?.description}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">Your Email</label>
          <input
            type="email"
            required
            value={userEmail}
            onChange={(e) => setUserEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">Title</label>
          <input
            type="text"
            required
            minLength={5}
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="Brief summary of the issue"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700">Description</label>
          <textarea
            required
            minLength={10}
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="Describe the issue in detail"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Processing through the agentic pipeline..." : "Submit Ticket"}
        </button>
      </form>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      {result && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Result: {result.ticket_id}</h2>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                result.requires_human_review
                  ? "bg-orange-100 text-orange-700"
                  : "bg-green-100 text-green-700"
              }`}
            >
              {result.requires_human_review ? "Escalated to human" : "Auto-resolved"}
            </span>
          </div>
          <p className="text-sm text-slate-600">
            Confidence: {(result.confidence_score * 100).toFixed(0)}% &middot; Processed in{" "}
            {result.processing_time_seconds.toFixed(1)}s &middot; Intent: {result.trace.intent} &middot;
            Priority: {result.trace.priority}
          </p>
          <div className="rounded-md bg-slate-50 p-4 text-sm text-slate-800 whitespace-pre-wrap">
            {result.drafted_response}
          </div>
          <Link
            href={`/tickets/${result.ticket_id}`}
            className="inline-block text-sm font-medium text-indigo-600 hover:underline"
          >
            View full agentic trace &rarr;
          </Link>
        </div>
      )}
    </div>
  );
}
