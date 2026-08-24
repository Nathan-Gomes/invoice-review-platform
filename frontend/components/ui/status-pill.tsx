import { cn } from "@/lib/utils";

type StatusKind = "critical" | "watch" | "good" | "neutral";

const KIND_STYLES: Record<StatusKind, string> = {
  critical: "bg-[var(--color-critical-soft)] text-[var(--color-critical)]",
  watch: "bg-[var(--color-watch-soft)] text-[var(--color-watch)]",
  good: "bg-[var(--color-good-soft)] text-[var(--color-good)]",
  neutral: "bg-[var(--color-neutral-status-soft)] text-[var(--color-neutral-status)]",
};

// Maps every status vocabulary in the product to one restrained visual language.
const TIER_KIND: Record<string, StatusKind> = {
  Critical: "critical",
  Watch: "watch",
  Informational: "neutral",
};
const INVOICE_STATE_KIND: Record<string, StatusKind> = {
  "Needs Review": "watch",
  Problem: "critical",
  Duplicate: "watch",
  Approved: "good",
  Rejected: "neutral",
};
const ACTION_STATUS_KIND: Record<string, StatusKind> = {
  New: "neutral",
  Investigating: "watch",
  Actioned: "watch",
  Resolved: "good",
};
const FINDING_STATUS_KIND: Record<string, StatusKind> = {
  New: "neutral",
  Reviewing: "watch",
  Pending: "watch",
  Recovered: "good",
  Closed: "good",
  Dismissed: "neutral",
};

function resolveKind(label: string): StatusKind {
  return (
    TIER_KIND[label] ||
    INVOICE_STATE_KIND[label] ||
    ACTION_STATUS_KIND[label] ||
    FINDING_STATUS_KIND[label] ||
    "neutral"
  );
}

export function StatusPill({ label, className }: { label: string; className?: string }) {
  const kind = resolveKind(label);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[12px] font-medium leading-5",
        KIND_STYLES[kind],
        className
      )}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: "currentColor" }}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function ConfidenceDots({ confidence }: { confidence: string }) {
  const filled = confidence === "Strong" ? 3 : confidence === "Likely" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-0.5" title={confidence} aria-label={`Confidence: ${confidence}`}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            i < filled ? "bg-[var(--color-ink-muted)]" : "bg-[var(--color-hairline-strong)]"
          )}
        />
      ))}
    </span>
  );
}
