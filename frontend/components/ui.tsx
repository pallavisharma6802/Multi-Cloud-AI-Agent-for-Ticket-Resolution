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
    <div className={`rounded-xl border border-line bg-surface shadow-card ${className}`}>
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
  // Neutral KPI tile: one accent color reserved for the single metric that
  // matters most (brand); everything else stays grayscale so the numbers
  // carry the weight, not the color.
  const iconBg: Record<string, string> = {
    default: "bg-ink-faint/10 text-ink-soft",
    brand: "bg-brand-100 text-brand-700",
    teal: "bg-ink-faint/10 text-ink-soft",
    amber: "bg-ink-faint/10 text-ink-soft",
    purple: "bg-ink-faint/10 text-ink-soft",
  };
  const valueTone: Record<string, string> = {
    default: "text-ink",
    brand: "text-brand-700",
    teal: "text-ink",
    amber: "text-ink",
    purple: "text-ink",
  };
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[11px] font-medium uppercase tracking-wide text-ink-faint">{label}</div>
        {Icon && (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${iconBg[tone]}`}>
            <Icon size={17} strokeWidth={2.25} />
          </span>
        )}
      </div>
      <div className={`mt-3 text-3xl font-semibold tracking-tight ${valueTone[tone]}`}>{value}</div>
      {foot && <div className="mt-1 text-xs text-ink-faint">{foot}</div>}
    </Card>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-priority-low/15 text-priority-low",
  medium: "bg-priority-medium/15 text-priority-medium",
  high: "bg-priority-high/15 text-priority-high",
  urgent: "bg-priority-urgent/15 text-priority-urgent",
};

export function PriorityBadge({ priority }: { priority: string }) {
  const key = (priority || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${
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
  open: "bg-line text-ink-soft",
  in_progress: "bg-priority-medium/15 text-[#92600a]",
  resolved: "bg-[#0d9488]/10 text-[#0d9488]",
  closed: "bg-line text-ink-soft",
};

export const STATUS_LABELS: Record<string, string> = {
  in_progress: "Needs review",
};

export function StatusBadge({ status }: { status: string }) {
  const key = (status || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide ${
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
    secondary: "bg-surface border border-line text-ink hover:border-ink-faint",
    ghost: "text-ink-soft hover:bg-line/60",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-wait disabled:opacity-50 ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-2xl">
        {eyebrow && (
          <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            {eyebrow}
          </div>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {description && <p className="mt-3 text-base leading-relaxed text-ink-soft">{description}</p>}
      </div>
      {action}
    </div>
  );
}
