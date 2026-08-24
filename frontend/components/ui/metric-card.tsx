import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  tone,
  className,
}: {
  label: string;
  value: string;
  tone?: "critical" | "watch" | "good" | "neutral";
  className?: string;
}) {
  const toneColor =
    tone === "critical"
      ? "text-[var(--color-critical)]"
      : tone === "watch"
        ? "text-[var(--color-watch)]"
        : tone === "good"
          ? "text-[var(--color-good)]"
          : "text-[var(--color-ink)]";

  return (
    <div className={cn("border border-[var(--color-hairline)] bg-[var(--color-surface)] rounded-md px-4 py-3", className)}>
      <div className="text-label mb-1">{label}</div>
      <div className={cn("text-2xl font-semibold tabular-nums", toneColor)}>{value}</div>
    </div>
  );
}
