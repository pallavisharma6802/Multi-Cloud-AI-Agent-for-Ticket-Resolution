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
  tone?: "default" | "brand" | "teal" | "amber";
  icon?: LucideIcon;
}) {
  const tones: Record<string, { bg: string; icon: string; value: string; border: string }> = {
    default: { bg: "bg-surface", icon: "bg-line/60 text-ink-soft", value: "text-ink", border: "" },
    brand: { bg: "bg-brand-gradient", icon: "bg-white/15 text-white", value: "text-white", border: "border-transparent shadow-glow" },
    teal: { bg: "bg-surface", icon: "bg-teal-100 text-teal-500", value: "text-ink", border: "border-l-2 border-l-teal-500/60" },
    amber: { bg: "bg-surface", icon: "bg-[#2b2008] text-priority-medium", value: "text-ink", border: "border-l-2 border-l-priority-medium/60" },
  };
  const t = tones[tone];
  const isBrand = tone === "brand";
  return (
    <Card className={`relative overflow-hidden p-6 ${t.bg} ${t.border}`}>
      <div className="flex items-start justify-between">
        <div className={`text-sm font-semibold ${isBrand ? "text-white/80" : "text-ink-soft"}`}>{label}</div>
        {Icon && (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${t.icon}`}>
            <Icon size={17} strokeWidth={2.25} />
          </span>
        )}
      </div>
      <div className={`mt-3 text-4xl font-bold tracking-tight ${t.value}`}>{value}</div>
      {foot && (
        <div className={`mt-1.5 text-sm ${isBrand ? "text-white/70" : "text-ink-faint"}`}>{foot}</div>
      )}
    </Card>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-teal-100 text-teal-500",
  medium: "bg-[#2b2008] text-priority-medium",
  high: "bg-[#2b1708] text-priority-high",
  urgent: "bg-[#2b0d12] text-priority-urgent",
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
  in_progress: "bg-[#2b2008] text-priority-medium",
  resolved: "bg-teal-100 text-teal-500",
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
