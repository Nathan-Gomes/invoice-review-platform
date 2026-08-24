import { cn } from "@/lib/utils";

export function StickyActionBar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "sticky bottom-0 left-0 right-0 flex items-center justify-between border-t border-[var(--color-hairline)] bg-[var(--color-surface)] px-5 py-3",
        className
      )}
    >
      {children}
    </div>
  );
}
