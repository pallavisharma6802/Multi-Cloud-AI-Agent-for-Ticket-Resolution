import { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-2xl border border-line bg-surface shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  foot,
  tone = "default",
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  foot?: string;
  tone?: "default" | "brand" | "teal" | "amber" | "purple";
  icon?: LucideIcon;
}) {
  // Flat KPI-tile style: neutral card, solid-colored icon badge carries the
  // color -- not the whole card -- so a row of these reads as a real support
  // dashboard (distinct colors per metric) rather than one brand wash.
  const iconBg: Record<string, string> = {
    default: "bg-ink-faint/20 text-ink-soft",
    brand: "bg-brand-500 text-white",
    teal: "bg-[#2fb66a] text-white",
    amber: "bg-priority-medium text-white",
    purple: "bg-[#8b5cf6] text-white",
  };
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-ink-soft">{label}</div>
        {Icon && (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconBg[tone]}`}>
            <Icon size={17} strokeWidth={2.25} />
          </span>
        )}
      </div>
      <div className="mt-3 text-3xl font-bold tracking-tight text-ink">{value}</div>
      {foot && <div className="mt-1 text-xs text-ink-faint">{foot}</div>}
    </Card>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-[#e0f2fe] text-[#0369a1]",
  medium: "bg-[#fef3c7] text-priority-medium",
  high: "bg-[#ffe4d5] text-priority-high",
  urgent: "bg-[#fee2e2] text-priority-urgent",
};

export function PriorityBadge({ priority }: { priority: string }) {
  const key = (priority || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
        PRIORITY_STYLES[key] || "bg-line/60 text-ink-soft"
      }`}
    >
      {priority || "none"}
    </span>
  );
}

// Real backend enum (app/schemas/ticket.py TicketStatus): open, in_progress,
// resolved, closed. in_progress specifically means "drafted a response but it
// needs human review" (set in app/api/routes/tickets.py when
// requires_human_review is true) -- there is no separate "needs_review" status.
const STATUS_STYLES: Record<string, string> = {
  open: "bg-line/60 text-ink-soft",
  in_progress: "bg-[#fef3c7] text-priority-medium",
  resolved: "bg-[#dcfce7] text-[#15803d]",
  closed: "bg-line/60 text-ink-soft",
};

export const STATUS_LABELS: Record<string, string> = {
  in_progress: "Needs review",
};

export function StatusBadge({ status }: { status: string }) {
  const key = (status || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
        STATUS_STYLES[key] || "bg-line/60 text-ink-soft"
      }`}
    >
      {STATUS_LABELS[key] || (status || "none").replace(/_/g, " ")}
    </span>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  const variants: Record<string, string> = {
    primary: "bg-brand-500 text-white hover:bg-brand-600 shadow-card",
    secondary: "bg-surface border border-line text-ink hover:border-brand-500/40",
    ghost: "text-ink-soft hover:bg-line/60",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:cursor-wait disabled:opacity-50 ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function PageHeading({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h1>
        {description && <p className="mt-3 text-lg leading-relaxed text-ink-soft">{description}</p>}
      </div>
      {action}
    </div>
  );
}
