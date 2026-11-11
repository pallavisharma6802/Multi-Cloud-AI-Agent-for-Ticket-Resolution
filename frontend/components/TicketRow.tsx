import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { TicketSummary } from "@/lib/api";
import { PriorityBadge, StatusBadge } from "./ui";

function initials(email: string) {
  const name = email.split("@")[0] || "?";
  return name.slice(0, 2).toUpperCase();
}

const BAR_COLORS: Record<string, string> = {
  resolved: "#22c55e",
  in_progress: "#f59e0b",
  closed: "#94a3b8",
  open: "#329dd2",
};

export default function TicketRow({ ticket }: { ticket: TicketSummary }) {
  const needsReview = ticket.status?.toLowerCase() === "in_progress";
  const barColor = BAR_COLORS[ticket.status?.toLowerCase()] || BAR_COLORS.open;
  return (
    <Link
      href={`/tickets/${ticket.ticket_id}`}
      style={{ borderLeft: `3px solid ${barColor}` }}
      className={`flex items-center gap-4 border-b border-line px-5 py-4 transition hover:bg-line/30 ${
        needsReview ? "bg-[#fef3c7]/50" : ""
      }`}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
        {initials(ticket.user_email)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`truncate text-sm ${needsReview ? "font-semibold text-ink" : "font-medium text-ink"}`}>
            {ticket.title}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-ink-soft">{ticket.description}</p>
      </div>
      <div className="hidden shrink-0 items-center gap-2 sm:flex">
        {ticket.priority && <PriorityBadge priority={ticket.priority} />}
        <StatusBadge status={ticket.status} />
      </div>
      <span className="hidden shrink-0 text-xs text-ink-faint md:block">
        {new Date(ticket.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
      </span>
      <ChevronRight size={16} className="shrink-0 text-ink-faint" />
    </Link>
  );
}
