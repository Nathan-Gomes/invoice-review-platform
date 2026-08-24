import { cn } from "@/lib/utils";

export function FieldGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
        {title}
      </div>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </div>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: number | undefined }) {
  if (confidence === undefined) return null;
  const low = confidence < 0.7;
  if (!low) return null;
  return (
    <span className="ml-1.5 rounded-sm bg-[var(--color-watch-soft)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--color-watch)]">
      low confidence
    </span>
  );
}

export function FieldWrapper({
  label,
  confidence,
  fullWidth,
  children,
}: {
  label: string;
  confidence?: number;
  fullWidth?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={cn(fullWidth && "col-span-2")}>
      <label className="text-label mb-1 flex items-center">
        {label}
        <ConfidenceBadge confidence={confidence} />
      </label>
      {children}
    </div>
  );
}
