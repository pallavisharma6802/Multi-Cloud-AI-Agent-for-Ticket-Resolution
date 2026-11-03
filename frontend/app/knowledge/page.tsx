"use client";
import { useEffect, useMemo, useState } from "react";

type Doc = {
  id: string;
  title: string;
  category: string;
  pack: string;
  source: string;
  preview: string;
};

const PAGE_SIZE = 40;

export default function Knowledge() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [selected, setSelected] = useState<Doc | null>(null);
  const [shown, setShown] = useState(PAGE_SIZE);

  useEffect(() => {
    fetch("/knowledge-map.json")
      .then((r) => {
        if (!r.ok) throw new Error("Unable to load the knowledge library");
        return r.json();
      })
      .then(setDocs)
      .catch((e) => setError(e.message));
  }, []);

  const categories = useMemo(
    () => Array.from(new Set(docs.map((d) => d.category))).sort(),
    [docs]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return docs.filter(
      (d) =>
        (category === "all" || d.category === category) &&
        (!q || (d.title + " " + d.preview).toLowerCase().includes(q))
    );
  }, [docs, query, category]);

  const visible = filtered.slice(0, shown);

  return (
    <div className="home-page">
      <div className="page-heading">
        <div>
          <h1>Knowledge library</h1>
          <p>
            Every document your assistant can cite, grounded in the official VS Code
            documentation. Search or filter by topic, then open a document to read its
            source.
          </p>
        </div>
      </div>

      <div className="button-row">
        <input
          className="btn"
          aria-label="Search the knowledge library"
          placeholder="Search documents"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShown(PAGE_SIZE);
          }}
        />
        <select
          className="btn"
          aria-label="Topic"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setShown(PAGE_SIZE);
          }}
        >
          <option value="all">All topics</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <p className="subtle">
        {filtered.length.toLocaleString()} documents · {categories.length} topics
      </p>
      {error && <p role="alert">{error}</p>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 12 }}>
        <div className="panel" style={{ overflow: "auto", maxHeight: 650, padding: 0 }}>
          {visible.length === 0 && !error && (
            <p style={{ padding: 20 }}>No documents match that search.</p>
          )}
          {visible.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelected(d)}
              className="text-link"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "14px 18px",
                borderBottom: "1px solid var(--line)",
                background: selected?.id === d.id ? "#edf4ff" : "transparent",
              }}
            >
              <strong style={{ display: "block" }}>{d.title}</strong>
              <span className="subtle">{d.category}</span>
            </button>
          ))}
          {shown < filtered.length && (
            <button className="btn" style={{ margin: 16 }} onClick={() => setShown((n) => n + PAGE_SIZE)}>
              Show more ({filtered.length - shown} remaining)
            </button>
          )}
        </div>

        <section className="panel" style={{ padding: 24, alignSelf: "start" }}>
          {selected ? (
            <>
              <h2>{selected.title}</h2>
              <p className="subtle">
                {selected.pack} · {selected.category}
              </p>
              <p style={{ fontSize: 16, lineHeight: 1.7 }}>{selected.preview}…</p>
              {/^https?:\/\//.test(selected.source) && (
                <a className="text-link" href={selected.source} target="_blank" rel="noreferrer">
                  Read the full source on GitHub ↗
                </a>
              )}
            </>
          ) : (
            <p>Select a document to preview it and open its source.</p>
          )}
        </section>
      </div>
    </div>
  );
}
