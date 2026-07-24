import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Multi-Cloud Ticket Resolution</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Submit support tickets through a multi-agent LangGraph pipeline: classification, retrieval,
          grading, drafting, judging, and escalation — with Azure NLP, Pinecone, and optional BigQuery analytics.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HomeCard
          href="/submit"
          title="Submit a Ticket"
          description="Pick a domain pack and submit a real support ticket through the live pipeline."
        />
        <HomeCard
          href="/triage"
          title="Triage Queue"
          description="Browse processed tickets, filter by domain/priority/status, and open any ticket's full trace."
        />
        <HomeCard
          href="/analytics"
          title="Analytics"
          description="Trend, agent-performance, RAG-health, and ops/cost dashboards backed by BigQuery + Grafana."
        />
      </div>
    </div>
  );
}

function HomeCard({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <Link
      href={href}
      className="block rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
    >
      <h2 className="font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
    </Link>
  );
}
