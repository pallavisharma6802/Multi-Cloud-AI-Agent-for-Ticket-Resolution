import { ReactNode } from "react";

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
}: {
  label: string;
  value: ReactNode;
  foot?: string;
  tone?: "default" | "brand" | "teal" | "amber";
}) {
  const tones: Record<string, string> = {
    default: "bg-surface",
    brand: "bg-brand-50",
    teal: "bg-teal-100",
    amber: "bg-amber-50",
  };
  return (
    <Card className={`p-5 ${tones[tone]}`}>
      <div className="text-sm font-medium text-ink-soft">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-ink">{value}</div>
      {foot && <div className="mt-1 text-xs text-ink-faint">{foot}</div>}
    </Card>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  low: "bg-teal-100 text-teal-500",
  medium: "bg-amber-50 text-priority-medium",
  high: "bg-orange-50 text-priority-high",
  urgent: "bg-rose-50 text-priority-urgent",
};

export function PriorityBadge({ priority }: { priority: string }) {
  const key = (priority || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
        PRIORITY_STYLES[key] || "bg-slate-100 text-ink-soft"
      }`}
    >
      {priority || "—"}
    </span>
  );
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-slate-100 text-ink-soft",
  resolved: "bg-teal-100 text-teal-500",
  ai_resolved: "bg-brand-50 text-brand-500",
  needs_review: "bg-amber-50 text-amber-600",
  escalated: "bg-rose-50 text-priority-urgent",
};

export function StatusBadge({ status }: { status: string }) {
  const key = (status || "").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
        STATUS_STYLES[key] || "bg-slate-100 text-ink-soft"
      }`}
    >
      {(status || "—").replace(/_/g, " ")}
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
    ghost: "text-ink-soft hover:bg-slate-100",
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
  description?: string;
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
