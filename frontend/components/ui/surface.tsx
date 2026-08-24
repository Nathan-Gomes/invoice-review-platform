import { cn } from "@/lib/utils";

/**
 * A full-width bordered section, not a floating card. Per the visual system:
 * "Avoid making every section a card. Use full-width sections with borders
 * and spacing." Use this for the container; put padding on the content, not
 * a heavy shadow.
 */
export function Surface({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)]",
        className
      )}
    >
      {children}
    </div>
  );
}

export function SurfaceHeader({
  title,
  action,
  className,
}: {
  title: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between border-b border-[var(--color-hairline)] px-4 py-3",
        className
      )}
    >
      <h2 className="text-section-title">{title}</h2>
      {action}
    </div>
  );
}
