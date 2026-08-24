"use client";

import { useQuery } from "@tanstack/react-query";
import { getOverview } from "@/lib/api";
import { MetricCard } from "@/components/ui/metric-card";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { StatusPill, ConfidenceDots } from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatPercent, formatDate, humanizeRule } from "@/lib/utils";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  BarChart, Bar,
} from "recharts";
import Link from "next/link";
import { AlertTriangle, ArrowRight } from "lucide-react";

export default function OverviewPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["overview"],
    queryFn: getOverview,
  });

  if (isLoading) {
    return <OverviewSkeleton />;
  }

  if (isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load the overview"
          message={(error as Error)?.message || "The backend may not be running."}
        />
      </div>
    );
  }

  if (!data) return null;

  const { metrics, needs_attention, portfolio_trend, category_breakdown, top_properties_by_excess, recent_actions } = data;

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-page-title">Overview</h1>
        {metrics.open_critical_incidents > 0 && (
          <Link href="/triage?tier=Critical">
            <Button variant="primary" size="sm">
              Review {metrics.open_critical_incidents} Critical incident{metrics.open_critical_incidents === 1 ? "" : "s"}
              <ArrowRight size={14} />
            </Button>
          </Link>
        )}
      </div>

      {/* Top row metrics */}
      <div className="mb-6 grid grid-cols-5 gap-3">
        <MetricCard label="Total monthly spend" value={formatCurrency(metrics.total_monthly_spend)} />
        <MetricCard
          label="Variance vs. last year"
          value={formatPercent(metrics.yoy_variance_pct)}
          tone={
            metrics.yoy_variance_pct === null
              ? "neutral"
              : metrics.yoy_variance_pct > 10
                ? "critical"
                : metrics.yoy_variance_pct > 0
                  ? "watch"
                  : "good"
          }
        />
        <MetricCard
          label="Estimated annual excess"
          value={formatCurrency(metrics.estimated_annual_excess)}
          tone={metrics.estimated_annual_excess > 0 ? "watch" : "good"}
        />
        <MetricCard
          label="Invoices awaiting review"
          value={String(metrics.invoices_needing_review)}
          tone={metrics.invoices_needing_review > 0 ? "watch" : "good"}
        />
        <MetricCard
          label="Open Critical incidents"
          value={String(metrics.open_critical_incidents)}
          tone={metrics.open_critical_incidents > 0 ? "critical" : "good"}
        />
      </div>

      {/* Needs Attention */}
      <Surface className="mb-6">
        <SurfaceHeader
          title="Needs attention"
          action={
            <Link href="/triage" className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">
              View all in Triage
            </Link>
          }
        />
        {needs_attention.length === 0 ? (
          <EmptyState
            icon={<AlertTriangle size={18} />}
            title="Nothing needs attention right now"
            message="Once invoices are approved and the triage scan runs, ranked issues will appear here."
          />
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                <th className="px-4 py-2 font-medium">Severity</th>
                <th className="px-4 py-2 font-medium">Property</th>
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 font-medium">Issue</th>
                <th className="px-4 py-2 font-medium">Cause</th>
                <th className="px-4 py-2 font-medium text-right">Est. impact</th>
                <th className="px-4 py-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {needs_attention.map((row, i) => (
                <tr key={i} className="border-b border-[var(--color-hairline)] last:border-0 hover:bg-[var(--color-surface-muted)]">
                  <td className="px-4 py-2.5"><StatusPill label={row.tier} /></td>
                  <td className="px-4 py-2.5">
                    <Link href={`/properties/${row.property_id}`} className="font-medium text-[var(--color-ink)] hover:text-[var(--color-brand)]">
                      {row.property_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-[var(--color-ink-muted)]">{row.category}</td>
                  <td className="px-4 py-2.5 max-w-[360px] truncate text-[var(--color-ink-muted)]" title={row.issue}>
                    {row.issue}
                  </td>
                  <td className="px-4 py-2.5 text-[var(--color-ink-muted)]">{row.cause}</td>
                  <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                    {formatCurrency(row.annualized_impact)}
                  </td>
                  <td className="px-4 py-2.5"><ConfidenceDots confidence={row.confidence} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Surface>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <Surface>
          <SurfaceHeader title="Monthly portfolio spend" />
          <div className="p-4">
            {portfolio_trend.length === 0 ? (
              <EmptyState title="No trend data yet" message="Approve invoices across a few months to see a trend." />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={portfolio_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(m) => formatDate(m)} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(v) => formatCurrency(v)} width={70} />
                  <Tooltip formatter={(v) => formatCurrency(typeof v === "number" ? v : undefined)} labelFormatter={(l) => formatDate(l as string)} />
                  <Line type="monotone" dataKey="total_cost" stroke="var(--color-brand)" strokeWidth={2} dot={false} name="Total cost" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Surface>

        <Surface>
          <SurfaceHeader title="Cost by utility category" />
          <div className="p-4">
            {category_breakdown.length === 0 ? (
              <EmptyState title="No category data yet" message="Approve invoices to see the category breakdown." />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={category_breakdown} layout="vertical" margin={{ left: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(v) => formatCurrency(v)} />
                  <YAxis type="category" dataKey="category" tick={{ fontSize: 12, fill: "var(--color-ink)" }} width={90} />
                  <Tooltip formatter={(v) => formatCurrency(typeof v === "number" ? v : undefined)} />
                  <Bar dataKey="total_cost" fill="var(--color-brand)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Surface>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Surface>
          <SurfaceHeader title="Properties driving the largest increase" />
          {top_properties_by_excess.length === 0 ? (
            <EmptyState title="No excess spending identified" message="This list populates once anomalies produce an estimated excess." />
          ) : (
            <ul className="divide-y divide-[var(--color-hairline)]">
              {top_properties_by_excess.map((p) => (
                <li key={p.property_id} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                  <Link href={`/properties/${p.property_id}`} className="font-medium hover:text-[var(--color-brand)]">
                    {p.property_name}
                  </Link>
                  <span className="tabular-nums text-[var(--color-watch)] font-medium">
                    {formatCurrency(p.observed_excess)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        <Surface>
          <SurfaceHeader
            title="Recently assigned actions"
            action={
              <Link href="/findings" className="text-[13px] font-medium text-[var(--color-brand)] hover:underline">
                View all
              </Link>
            }
          />
          {recent_actions.length === 0 ? (
            <EmptyState title="No actions assigned yet" message="Create an action from a finding in Triage or Findings." />
          ) : (
            <ul className="divide-y divide-[var(--color-hairline)]">
              {recent_actions.map((a) => (
                <li key={a.id} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                  <div>
                    <div className="font-medium">{a.action_taken}</div>
                    <div className="text-metadata">{a.property_name} · {a.owner || "Unassigned"}</div>
                  </div>
                  <StatusPill label={a.status} />
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>
    </div>
  );
}

function EmptyState({ icon, title, message }: { icon?: React.ReactNode; title: string; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-[var(--color-ink-faint)]">{icon}</div>}
      <div className="text-[13.5px] font-medium text-[var(--color-ink)]">{title}</div>
      <div className="max-w-sm text-[13px] text-[var(--color-ink-faint)]">{message}</div>
    </div>
  );
}

function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <Surface className="p-6">
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="mt-0.5 text-[var(--color-critical)]" />
        <div>
          <div className="text-section-title mb-1">{title}</div>
          <div className="text-[13px] text-[var(--color-ink-muted)]">{message}</div>
        </div>
      </div>
    </Surface>
  );
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <div className="mb-5 h-7 w-32 animate-pulse rounded-md bg-[var(--color-hairline)]" />
      <div className="mb-6 grid grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface-muted)]" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface-muted)]" />
    </div>
  );
}
