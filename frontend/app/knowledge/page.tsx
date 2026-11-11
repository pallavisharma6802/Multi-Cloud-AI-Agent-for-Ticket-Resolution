"use client";
import { useEffect, useState } from "react";
import { ExternalLink, BookOpen, RefreshCw } from "lucide-react";
import { getKnowledgeBase, KnowledgeBaseInfo } from "@/lib/api";
import { Card, PageHeading } from "@/components/ui";

const CATEGORY_LABELS: Record<string, string> = {
  AI_FEATURES: "AI features",
  API_REFERENCE: "API reference",
  REMOTE_CLOUD: "Remote & cloud",
  GETTING_STARTED: "Getting started",
  RELEASE_NOTES: "Release notes",
};

const CATEGORY_COLORS = ["#e3a655", "#a78bfa", "#2dd4bf", "#fb923c", "#e78fa3", "#f2b84b", "#22d3ee"];

function label(category: string) {
  return CATEGORY_LABELS[category] || category.charAt(0) + category.slice(1).toLowerCase().replace(/_/g, " ");
}

export default function Knowledge() {
  const [data, setData] = useState<KnowledgeBaseInfo | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getKnowledgeBase(30)
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const categories = data
    ? Object.entries(data.category_counts).sort((a, b) => b[1] - a[1])
    : [];
  const maxCount = categories.length ? categories[0][1] : 1;

  return (
    <div>
      <PageHeading
        title="Knowledge base"
        description="Every answer this agent drafts is grounded in these documents. Nothing else, no private data, no made-up sources."
      />

      {loading && (
        <Card className="p-10 text-center text-sm text-ink-soft">
          <RefreshCw size={16} className="mx-auto mb-2 animate-spin" />
          Loading knowledge base…
        </Card>
      )}

      {error && (
        <Card className="border-priority-urgent/30 bg-priority-urgent/10 p-4 text-sm text-priority-urgent">
          Couldn&apos;t load the knowledge base: {error}
        </Card>
      )}

      {data && (
        <>
          <Card className="mb-6 p-6">
            <div className="flex items-center gap-2">
              <BookOpen size={16} className="text-brand-500" />
              <h2 className="text-xs font-bold uppercase tracking-widest text-brand-500">Source &amp; provenance</h2>
            </div>
            <p className="mt-3 text-base text-ink-soft">
              {data.total_documents.toLocaleString()} documents, chunked from{" "}
              <span className="font-semibold text-ink">{data.source_dataset.name}</span>: real,
              official, licensed documentation, not a synthetic or scraped dataset.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-soft">
              <a
                href={data.source_dataset.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 font-semibold text-brand-500 hover:text-brand-600"
              >
                View source repo <ExternalLink size={13} />
              </a>
              <span>License: {data.source_dataset.license}</span>
              <span>{data.source_dataset.num_source_rows.toLocaleString()} source pages/chunks</span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-ink-faint">{data.source_dataset.limitations}</p>
          </Card>

          <Card className="mb-6 p-6">
            <h2 className="text-xs font-bold uppercase tracking-widest text-ink-faint">Coverage by category</h2>
            <div className="mt-4 space-y-2.5">
              {categories.map(([cat, count], i) => (
                <div key={cat} className="flex items-center gap-3">
                  <span className="flex w-36 shrink-0 items-center gap-2 text-sm text-ink-soft">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
                    />
                    {label(cat)}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-line/60">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(4, (count / maxCount) * 100)}%`,
                        background: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                      }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right text-sm font-semibold text-ink">{count}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <div className="border-b border-line px-6 py-5">
              <h2 className="text-lg font-semibold text-ink">A sample of the real documents</h2>
              <p className="text-sm text-ink-soft">
                Randomly sampled from the full {data.total_documents.toLocaleString()}; each links to the exact
                commit of the source file.
              </p>
            </div>
            <div className="divide-y divide-line">
              {data.sample.map((doc) => (
                <a
                  key={doc.id}
                  href={doc.source}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between gap-4 px-6 py-3.5 transition hover:bg-brand-50/40"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{doc.title}</div>
                    <div className="mt-0.5 text-xs text-ink-faint">{label(doc.category)}</div>
                  </div>
                  <ExternalLink size={14} className="shrink-0 text-ink-faint" />
                </a>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
