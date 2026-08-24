"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, ListChecks, Building2, FileText, LineChart,
  ClipboardList, Settings as SettingsIcon, CircleUser,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Monitor",
    items: [
      { href: "/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/triage", label: "Triage", icon: ListChecks },
    ],
  },
  {
    label: "Investigate",
    items: [
      { href: "/properties", label: "Properties", icon: Building2 },
      { href: "/invoices", label: "Invoices", icon: FileText },
      { href: "/analysis", label: "Analysis", icon: LineChart },
    ],
  },
  {
    label: "Manage",
    items: [{ href: "/findings", label: "Findings & Actions", icon: ClipboardList }],
  },
  {
    label: "System",
    items: [{ href: "/settings", label: "Settings", icon: SettingsIcon }],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [operatorName, setOperatorName] = useState("");

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-[var(--color-hairline)] bg-[var(--color-surface)]">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-[var(--color-brand)] text-[11px] font-bold text-white">
          IR
        </div>
        <span className="text-[15px] font-semibold text-[var(--color-ink)]">Invoice Review</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
              {group.label}
            </div>
            {group.items.map((item) => {
              const active = pathname?.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13.5px] font-medium transition-colors",
                    active
                      ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                      : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink)]"
                  )}
                >
                  <Icon size={16} className={active ? "text-[var(--color-brand)]" : "text-[var(--color-ink-faint)]"} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-[var(--color-hairline)] px-3 py-3">
        <div className="mb-2 flex items-center gap-2 px-1">
          <span className="rounded-sm bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--color-ink-faint)] border border-[var(--color-hairline)]">
            demo
          </span>
          <span className="text-[11px] text-[var(--color-ink-faint)]">environment</span>
        </div>
        <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
          <CircleUser size={18} className="text-[var(--color-ink-faint)]" />
          <input
            value={operatorName}
            onChange={(e) => {
              setOperatorName(e.target.value);
              if (typeof window !== "undefined") {
                window.localStorage.setItem("operatorName", e.target.value);
              }
            }}
            placeholder="Your name"
            className="w-full bg-transparent text-[13px] text-[var(--color-ink)] placeholder:text-[var(--color-ink-faint)] focus:outline-none"
          />
        </div>
      </div>
    </aside>
  );
}
