"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { API_BASE_URL } from "@/lib/api";
const links = [
  { href: "/", label: "Overview", icon: "grid" },
  { href: "/triage", label: "Ticket inbox", icon: "inbox" },
  { href: "/analytics", label: "Analytics", icon: "chart" },
];
export default function NavBar() {
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
    <>
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <Icon name="spark" size={23} />
          </span>
          resolve<span className="brand-dot">.</span>
        </Link>
        <div className="workspace">
          <span className="workspace-avatar">S</span>
          <div>
            Support workspace<small>Multi-cloud operations</small>
          </div>
          <span className="workspace-chevron">⌄</span>
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`nav-link ${(l.href === "/" ? path === "/" : path.startsWith(l.href)) ? "active" : ""}`}
            >
              <Icon name={l.icon} />
              {l.label}
              {l.href === "/triage" && <span className="nav-key">⌘ K</span>}
            </Link>
          ))}
        </nav>
        <Link href="/submit" className="sidebar-create">
          <Icon name="plus" size={17} /> Create ticket
        </Link>
        <div className="sidebar-bottom">
          <div className="agent-note">
            <Icon name="shield" />
            <strong>AI with accountability</strong>
            <p>Every resolution comes with evidence and a decision trail.</p>
            <Link href="/triage">
              Explore the inbox <span>↗</span>
            </Link>
          </div>
          <div className="profile">
            <span className="user-avatar">PS</span>
            <div>
              Support team<small>Workspace administrator</small>
            </div>
          </div>
        </div>
      </aside>
      <header className="topbar">
        <div className="breadcrumbs">
          Workspace <span>/</span>{" "}
          <strong>
            {path === "/"
              ? "Overview"
              : path.startsWith("/tickets")
                ? "Ticket details"
                : path === "/triage"
                  ? "Ticket inbox"
                  : path === "/submit"
                    ? "Create ticket"
                    : "Analytics"}
          </strong>
        </div>
        <div className="topbar-right">
          <span className={`live-state ${online ? "online" : ""}`}>
            <i />
            {online ? "API connected" : "Connecting to API"}
          </span>
          <span className="topbar-avatar">PS</span>
        </div>
      </header>
    </>
  );
}
