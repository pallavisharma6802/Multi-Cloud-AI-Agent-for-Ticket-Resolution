"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutGrid,
  Inbox,
  Sparkles,
  Plus,
  ShieldCheck,
  ArrowUpRight,
  UserRound,
  BookOpen,
  Columns3,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/api";
import Mascot from "./Mascot";

const links = [
  { href: "/overview", label: "Overview", icon: LayoutGrid, color: "#8a5c1c", tint: "rgba(203,138,46,0.12)" },
  { href: "/triage", label: "Inbox", icon: Inbox, color: "#6d28d9", tint: "rgba(124,58,237,0.1)" },
  { href: "/review", label: "Review board", icon: Columns3, color: "#b45309", tint: "rgba(217,119,6,0.1)" },
  { href: "/knowledge", label: "Knowledge base", icon: BookOpen, color: "#0d7a70", tint: "rgba(13,148,136,0.1)" },
];

const titles: Record<string, string> = {
  "/": "Home",
  "/overview": "Overview",
  "/triage": "Inbox",
  "/review": "Review board",
  "/submit": "New ticket",
  "/knowledge": "Knowledge base",
};

function titleFor(path: string) {
  if (titles[path]) return titles[path];
  if (path.startsWith("/tickets")) return "Ticket";
  return "Resolve";
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [online, setOnline] = useState(false);

  useEffect(() => {
    const check = () =>
      fetch(`${API_BASE_URL}/health`)
        .then((r) => setOnline(r.ok))
        .catch(() => setOnline(false));
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-line bg-surface px-4 py-6 text-ink-soft">
        <Link href="/" className="flex items-center gap-2 px-2 font-serif text-xl font-semibold tracking-tight text-ink">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-gradient text-[#fff8ec] shadow-glow">
            <Sparkles size={15} strokeWidth={2.5} />
          </span>
          resolve
        </Link>
        <span className="mt-1.5 px-2 font-mono text-[10px] uppercase tracking-wider text-ink-faint">
          Example build · VS Code support
        </span>

        <Link
          href="/submit"
          className="mt-6 flex items-center justify-center gap-2 rounded-full bg-brand-500 px-4 py-2.5 font-mono text-xs font-medium uppercase tracking-wide text-[#fff8ec] shadow-card transition hover:bg-brand-600"
        >
          <Plus size={16} /> New ticket
        </Link>

        <div className="mt-8 px-2 font-mono text-[10px] uppercase tracking-wider text-ink-faint">
          Workspace
        </div>
        <nav className="mt-2 flex flex-col gap-1">
          {links.map((l) => {
            const active = path.startsWith(l.href);
            const LinkIcon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  active ? "bg-line/60 text-ink shadow-card" : "text-ink-soft hover:bg-line/40 hover:text-ink"
                }`}
              >
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                  style={{ background: l.tint, color: l.color }}
                >
                  <LinkIcon size={15} strokeWidth={2.25} />
                </span>
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-4">
          <div className="rounded-xl border border-line bg-brand-50 p-4 text-sm">
            <div className="flex items-center gap-2 font-semibold text-ink">
              <ShieldCheck size={16} className="text-brand-500" />
              AI with accountability
            </div>
            <p className="mt-2 text-xs leading-relaxed text-ink-soft">
              Every resolution ships with evidence and a decision trail.
            </p>
            <Link
              href="/triage"
              className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-500"
            >
              Explore the inbox <ArrowUpRight size={13} />
            </Link>
          </div>
          <div className="flex items-center gap-3 border-t border-line pt-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-line/70 text-ink-soft">
              <UserRound size={16} />
            </span>
            <div className="text-sm">
              <div className="font-medium text-ink">Anonymous workspace</div>
              <div className="text-xs text-ink-faint">No sign-in, single shared demo</div>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-ink-faint">
            No accounts or profile pages. This is a single-tenant demo of the resolution
            pipeline, not a multi-user product. Each ticket already carries its own
            submitter email.
          </p>
        </div>
      </aside>

      <div className="flex min-h-screen flex-1 flex-col pl-64">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface/90 px-8 py-4 backdrop-blur">
          <div className="text-sm text-ink-soft">
            Workspace <span className="mx-1 text-ink-faint">/</span>
            <span className="font-medium text-ink">{titleFor(path || "/")}</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-2 text-xs font-medium text-ink-soft">
              <i
                className={`h-2 w-2 rounded-full ${online ? "bg-[#22c55e]" : "bg-priority-medium"}`}
              />
              {online ? "API connected" : "Connecting to API"}
            </span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-brand-700">
              <UserRound size={16} />
            </span>
          </div>
        </header>
        <main className="flex-1 px-8 py-8">{children}</main>
      </div>
      <Mascot />
    </div>
  );
}
