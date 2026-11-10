"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutGrid,
  Inbox,
  BarChart3,
  Sparkles,
  Plus,
  ShieldCheck,
  ArrowUpRight,
  UserRound,
  BookOpen,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

const links = [
  { href: "/", label: "Overview", icon: LayoutGrid },
  { href: "/triage", label: "Inbox", icon: Inbox },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/knowledge", label: "Knowledge base", icon: BookOpen },
];

const titles: Record<string, string> = {
  "/": "Overview",
  "/triage": "Inbox",
  "/analytics": "Analytics",
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
      <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-brand-900 bg-[radial-gradient(ellipse_400px_280px_at_0%_0%,rgba(36,91,219,0.35),transparent)] px-4 py-6 text-brand-100">
        <Link href="/" className="flex items-center gap-2.5 px-2 text-2xl font-bold tracking-tight text-white">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-gradient text-brand-900 shadow-glow">
            <Sparkles size={19} strokeWidth={2.5} />
          </span>
          resolve
        </Link>
        <span className="mt-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-teal-400">
          Example build · VS Code support
        </span>

        <Link
          href="/submit"
          className="mt-6 flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-card transition hover:bg-brand-600"
        >
          <Plus size={16} /> New ticket
        </Link>

        <div className="mt-8 px-2 text-xs font-semibold uppercase tracking-wider text-brand-100/50">
          Workspace
        </div>
        <nav className="mt-2 flex flex-col gap-1">
          {links.map((l) => {
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            const LinkIcon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                  active
                    ? "bg-brand-500 text-white shadow-card"
                    : "text-brand-100/80 hover:bg-white/5 hover:text-white"
                }`}
              >
                <LinkIcon size={18} strokeWidth={2} />
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-4">
          <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
            <div className="flex items-center gap-2 font-semibold text-white">
              <ShieldCheck size={16} className="text-teal-400" />
              AI with accountability
            </div>
            <p className="mt-2 text-xs leading-relaxed text-brand-100/70">
              Every resolution ships with evidence and a decision trail.
            </p>
            <Link
              href="/triage"
              className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-teal-400 hover:text-teal-100"
            >
              Explore the inbox <ArrowUpRight size={13} />
            </Link>
          </div>
          <div className="flex items-center gap-3 border-t border-white/10 pt-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-brand-100">
              <UserRound size={16} />
            </span>
            <div className="text-sm">
              <div className="font-medium text-white">Anonymous workspace</div>
              <div className="text-xs text-brand-100/60">No sign-in, single shared demo</div>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-brand-100/40">
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
                className={`h-2 w-2 rounded-full ${online ? "bg-teal-500" : "bg-amber-400"}`}
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
    </div>
  );
}
