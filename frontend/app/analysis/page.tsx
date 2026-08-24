"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { listProperties, getPropertyMonths, getPropertyAnalysis, getPropertyTrend } from "@/lib/api";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { Select } from "@/components/ui/input";
import { formatCurrency, formatPercent, formatDate } from "@/lib/utils";

const CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"];

export default function AnalysisPage() {
  const { data: properties } = useQuery({ queryKey: ["properties"], queryFn: listProperties });
  const [propertyId, setPropertyId] = useState<number | null>(null);
  const [category, setCategory] = useState("Water");
  const [month, setMonth] = useState<string | null>(null);

  const activePropertyId = propertyId ?? properties?.[0]?.id ?? null;

  const { data: months } = useQuery({
    queryKey: ["property-months", activePropertyId, category],
    queryFn: () => getPropertyMonths(activePropertyId!, category),
    enabled: !!activePropertyId,
  });
  const effectiveMonth = month || (months && months.length > 0 ? months[months.length - 1] : null);

  const { data: metrics } = useQuery({
    queryKey: ["property-analysis", activePropertyId, category, effectiveMonth],
    queryFn: () => getPropertyAnalysis(activePropertyId!, category, effectiveMonth!),
    enabled: !!activePropertyId && !!effectiveMonth,
  });

  const { data: trend } = useQuery({
    queryKey: ["property-trend", activePropertyId, category],
    queryFn: () => getPropertyTrend(activePropertyId!, category, 24),
    enabled: !!activePropertyId,
  });

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <h1 className="text-page-title mb-1">Analysis</h1>
      <p className="text-metadata mb-4">
        Ad hoc lookup across any property/category/month. For a curated view, use the property&apos;s workspace.
      </p>

      <div className="mb-4 flex gap-3">
        <Select value={activePropertyId ?? ""} onChange={(e) => { setPropertyId(Number(e.target.value)); setMonth(null); }} className="w-52">
          {(properties || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
        <Select value={category} onChange={(e) => { setCategory(e.target.value); setMonth(null); }} className="w-44">
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select value={effectiveMonth || ""} onChange={(e) => setMonth(e.target.value)} className="w-36">
          {(months || []).slice().reverse().map((m) => <option key={m} value={m}>{formatDate(m)}</option>)}
        </Select>
      </div>

      {!metrics ? (
        <Surface className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">
          No approved invoices yet for this property/category.
        </Surface>
      ) : (
        <>
          <Surface className="mb-4">
            <div className="grid grid-cols-4 gap-4 p-5">
              <Metric label="Total cost" value={formatCurrency(metrics.total_cost)} />
              <Metric label="Cost / occupied unit" value={metrics.cost_per_occupied_unit !== null ? formatCurrency(metrics.cost_per_occupied_unit) : "—"} />
              <Metric label="Usage / unit / day" value={metrics.usage_per_unit_per_day !== null ? metrics.usage_per_unit_per_day.toFixed(2) : "—"} />
              <Metric label="Effective rate" value={metrics.effective_rate !== null ? `$${metrics.effective_rate.toFixed(4)}` : "—"} />
              <Metric label="YoY variance" value={formatPercent(metrics.yoy_variance_pct)} />
              <Metric label="Observed excess" value={metrics.observed_excess !== null ? formatCurrency(metrics.observed_excess) : "—"} />
              <Metric label="Cause" value={metrics.cause} />
              <Metric label="Baseline confidence" value={metrics.baseline_confidence} />
            </div>
            <div className="border-t border-[var(--color-hairline)] px-5 py-3 text-[13px] text-[var(--color-ink-muted)]">
              {metrics.explanation}
            </div>
          </Surface>

          <Surface>
            <SurfaceHeader title="24-month cost trend" />
            <div className="p-4">
              {!trend || trend.length === 0 ? (
                <div className="p-6 text-center text-[13px] text-[var(--color-ink-faint)]">No trend data yet.</div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={trend}>
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
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-label mb-0.5">{label}</div>
      <div className="text-[16px] font-semibold">{value}</div>
    </div>
  );
}
