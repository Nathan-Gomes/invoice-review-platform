"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  BarChart, Bar,
} from "recharts";
import {
  getProperty, getPropertyTrend, getPropertyMonths, getPropertyAnalysis,
  getPropertyOccupancy, upsertOccupancy, listInvoices, listFindings, listActions,
} from "@/lib/api";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import { formatCurrency, formatPercent, formatDate } from "@/lib/utils";
import Link from "next/link";

const CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"];
const TABS = ["Summary", "Utilities", "Invoices", "Occupancy", "Findings & Actions"] as const;
type Tab = (typeof TABS)[number];

export default function PropertyDetailPage() {
  const params = useParams<{ propertyId: string }>();
  const propertyId = Number(params.propertyId);
  const [tab, setTab] = useState<Tab>("Summary");

  const { data: detail, isLoading } = useQuery({
    queryKey: ["property", propertyId],
    queryFn: () => getProperty(propertyId),
  });
  const { data: occupancy } = useQuery({
    queryKey: ["property-occupancy", propertyId],
    queryFn: () => getPropertyOccupancy(propertyId),
  });

  if (isLoading || !detail) {
    return (
      <div className="mx-auto max-w-[1400px] p-6">
        <div className="h-8 w-48 animate-pulse rounded-md bg-[var(--color-hairline)]" />
      </div>
    );
  }

  const currentTotal = detail.current_month_by_category.reduce((sum, c) => sum + c.total_cost, 0);
  const avgYoy = (() => {
    const values = detail.current_month_by_category.map((c) => c.yoy_variance_pct).filter((v): v is number => v !== null);
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  })();
  const latestOccupancy = occupancy && occupancy.length > 0 ? occupancy[occupancy.length - 1] : null;
  const topDriver = [...detail.current_month_by_category].sort((a, b) => (b.observed_excess || 0) - (a.observed_excess || 0))[0];

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      {/* Header */}
      <Surface className="mb-5 p-5">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h1 className="text-page-title">{detail.property.name}</h1>
            <div className="text-metadata mt-0.5">{detail.property.address || "No address on file"}</div>
          </div>
        </div>
        <div className="grid grid-cols-5 gap-4">
          <HeaderStat label="Units" value={detail.property.units ? String(detail.property.units) : "—"} />
          <HeaderStat
            label="Current occupancy"
            value={latestOccupancy ? `${latestOccupancy.occupied_units}/${detail.property.units ?? "—"}` : "—"}
          />
          <HeaderStat label="Current-month spend" value={formatCurrency(currentTotal)} />
          <HeaderStat
            label="YoY variance"
            value={formatPercent(avgYoy)}
            tone={avgYoy === null ? undefined : avgYoy > 10 ? "critical" : avgYoy > 0 ? "watch" : "good"}
          />
          <HeaderStat
            label="Open incidents"
            value={String(detail.open_incident_count)}
            tone={detail.open_incident_count > 0 ? "watch" : "good"}
          />
        </div>
      </Surface>

      {/* Tabs */}
      <div className="mb-4 flex gap-1 rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)] p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-sm px-3 py-1.5 text-[13px] font-medium transition-colors ${
              tab === t
                ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Summary" && <SummaryTab propertyId={propertyId} categoryBreakdown={detail.current_month_by_category} topDriver={topDriver} />}
      {tab === "Utilities" && <UtilitiesTab propertyId={propertyId} />}
      {tab === "Invoices" && <InvoicesTab propertyId={propertyId} />}
      {tab === "Occupancy" && <OccupancyTab propertyId={propertyId} propertyUnits={detail.property.units} occupancy={occupancy || []} />}
      {tab === "Findings & Actions" && <FindingsActionsTab propertyId={propertyId} />}
    </div>
  );
}

function HeaderStat({ label, value, tone }: { label: string; value: string; tone?: "critical" | "watch" | "good" }) {
  const color =
    tone === "critical" ? "text-[var(--color-critical)]" : tone === "watch" ? "text-[var(--color-watch)]" : tone === "good" ? "text-[var(--color-good)]" : "text-[var(--color-ink)]";
  return (
    <div>
      <div className="text-label mb-0.5">{label}</div>
      <div className={`text-[17px] font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

// ------------------------------------------------------------------ Summary
function SummaryTab({
  propertyId,
  categoryBreakdown,
  topDriver,
}: {
  propertyId: number;
  categoryBreakdown: { category: string; total_cost: number }[];
  topDriver?: { category: string; observed_excess: number | null };
}) {
  const router = useRouter();
  const [category, setCategory] = useState("Water");
  const { data: trend } = useQuery({
    queryKey: ["property-trend", propertyId, category],
    queryFn: () => getPropertyTrend(propertyId, category),
  });
  const { data: invoices } = useQuery({
    queryKey: ["invoices-by-property", propertyId],
    queryFn: () => listInvoices({ property_id: propertyId }),
  });
  const recent = (invoices || []).slice(0, 5);

  return (
    <div className="space-y-4">
      <Surface>
        <SurfaceHeader
          title="12-month trend: actual vs. expected"
          action={
            <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-40">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          }
        />
        <div className="p-4">
          {!trend || trend.length === 0 ? (
            <div className="p-6 text-center text-[13px] text-[var(--color-ink-faint)]">
              No approved {category} invoices yet.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                data={trend}
                onClick={(state) => {
                  const idx = state?.activeTooltipIndex;
                  if (typeof idx === "number" && trend[idx]) {
                    router.push(`/invoices/${trend[idx].invoice_id}`);
                  }
                }}
                style={{ cursor: "pointer" }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(m) => formatDate(m)} />
                <YAxis tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(v) => formatCurrency(v)} width={70} />
                <Tooltip formatter={(v) => formatCurrency(typeof v === "number" ? v : undefined)} labelFormatter={(l) => formatDate(l as string)} />
                <Line type="monotone" dataKey="total_cost" name="Actual" stroke="var(--color-brand)" strokeWidth={2} dot />
                <Line type="monotone" dataKey="expected_cost" name="Expected" stroke="var(--color-ink-faint)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
          <div className="mt-1 text-metadata">Click a point on the &ldquo;Actual&rdquo; line to open its invoice.</div>
        </div>
      </Surface>

      <div className="grid grid-cols-2 gap-4">
        <Surface>
          <SurfaceHeader title="Category breakdown" />
          <div className="p-4">
            {categoryBreakdown.length === 0 ? (
              <div className="p-6 text-center text-[13px] text-[var(--color-ink-faint)]">No data yet.</div>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={categoryBreakdown} layout="vertical" margin={{ left: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: "var(--color-ink-faint)" }} tickFormatter={(v) => formatCurrency(v)} />
                  <YAxis type="category" dataKey="category" tick={{ fontSize: 12 }} width={90} />
                  <Tooltip formatter={(v) => formatCurrency(typeof v === "number" ? v : undefined)} />
                  <Bar dataKey="total_cost" fill="var(--color-brand)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
            {topDriver && (
              <div className="mt-3 text-[13px] text-[var(--color-ink-muted)]">
                Top cost driver: <span className="font-medium text-[var(--color-ink)]">{topDriver.category}</span>
              </div>
            )}
          </div>
        </Surface>

        <Surface>
          <SurfaceHeader title="Recent invoice activity" />
          {recent.length === 0 ? (
            <div className="p-6 text-center text-[13px] text-[var(--color-ink-faint)]">No invoices yet.</div>
          ) : (
            <ul className="divide-y divide-[var(--color-hairline)]">
              {recent.map((inv) => (
                <li key={inv.id} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                  <Link href={`/invoices/${inv.id}`} className="font-medium hover:text-[var(--color-brand)]">
                    {inv.vendor} · {formatDate(inv.billing_start)}
                  </Link>
                  <span className="tabular-nums">{formatCurrency(inv.total_cost)}</span>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Utilities
function UtilitiesTab({ propertyId }: { propertyId: number }) {
  const [category, setCategory] = useState("Water");
  const { data: months } = useQuery({
    queryKey: ["property-months", propertyId, category],
    queryFn: () => getPropertyMonths(propertyId, category),
  });
  const [month, setMonth] = useState<string | null>(null);
  const effectiveMonth = month || (months && months.length > 0 ? months[months.length - 1] : null);

  const { data: metrics } = useQuery({
    queryKey: ["property-analysis", propertyId, category, effectiveMonth],
    queryFn: () => getPropertyAnalysis(propertyId, category, effectiveMonth!),
    enabled: !!effectiveMonth,
  });

  return (
    <Surface>
      <SurfaceHeader
        title="Utility analysis"
        action={
          <div className="flex gap-2">
            <Select value={category} onChange={(e) => { setCategory(e.target.value); setMonth(null); }} className="w-40">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
            <Select value={effectiveMonth || ""} onChange={(e) => setMonth(e.target.value)} className="w-32">
              {(months || []).slice().reverse().map((m) => <option key={m} value={m}>{formatDate(m)}</option>)}
            </Select>
          </div>
        }
      />
      <div className="p-4">
        {!metrics ? (
          <div className="p-6 text-center text-[13px] text-[var(--color-ink-faint)]">No data for this category/month.</div>
        ) : (
          <>
            <div className="mb-4 grid grid-cols-4 gap-3">
              <MiniMetric label="Total cost" value={formatCurrency(metrics.total_cost)} />
              <MiniMetric label="Cost / occupied unit" value={metrics.cost_per_occupied_unit !== null ? formatCurrency(metrics.cost_per_occupied_unit) : "—"} />
              <MiniMetric label="Usage / unit / day" value={metrics.usage_per_unit_per_day !== null ? metrics.usage_per_unit_per_day.toFixed(2) : "—"} />
              <MiniMetric label="Effective rate" value={metrics.effective_rate !== null ? `$${metrics.effective_rate.toFixed(4)}` : "—"} />
              <MiniMetric label="YoY variance" value={formatPercent(metrics.yoy_variance_pct)} />
              <MiniMetric label="Observed excess" value={metrics.observed_excess !== null ? formatCurrency(metrics.observed_excess) : "—"} />
              <MiniMetric label="Cause" value={metrics.cause} />
              <MiniMetric label="Baseline confidence" value={metrics.baseline_confidence} />
            </div>
            <div className="rounded-md bg-[var(--color-surface-muted)] px-3 py-2.5 text-[13px] text-[var(--color-ink-muted)]">
              {metrics.explanation}
            </div>
          </>
        )}
      </div>
    </Surface>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-label mb-0.5">{label}</div>
      <div className="text-[14px] font-semibold">{value}</div>
    </div>
  );
}

// ----------------------------------------------------------------- Invoices
function InvoicesTab({ propertyId }: { propertyId: number }) {
  const { data: invoices, isLoading } = useQuery({
    queryKey: ["invoices-by-property", propertyId],
    queryFn: () => listInvoices({ property_id: propertyId }),
  });

  return (
    <Surface>
      {isLoading ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
      ) : !invoices || invoices.length === 0 ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">No invoices for this property yet.</div>
      ) : (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[var(--color-hairline)] text-left text-label">
              <th className="px-4 py-2 font-medium">Vendor</th>
              <th className="px-2 py-2 font-medium">Category</th>
              <th className="px-2 py-2 font-medium">Billing period</th>
              <th className="px-2 py-2 font-medium text-right">Total</th>
              <th className="px-2 py-2 font-medium">State</th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => (
              <tr key={inv.id} className="border-b border-[var(--color-hairline)] last:border-0 hover:bg-[var(--color-surface-muted)]">
                <td className="px-4 py-2.5">
                  <Link href={`/invoices/${inv.id}`} className="font-medium hover:text-[var(--color-brand)]">{inv.vendor}</Link>
                </td>
                <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{inv.category}</td>
                <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{formatDate(inv.billing_start)} – {formatDate(inv.billing_end)}</td>
                <td className="px-2 py-2.5 text-right font-medium tabular-nums">{formatCurrency(inv.total_cost)}</td>
                <td className="px-2 py-2.5"><StatusPill label={inv.state} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Surface>
  );
}

// ---------------------------------------------------------------- Occupancy
function OccupancyTab({
  propertyId,
  propertyUnits,
  occupancy,
}: {
  propertyId: number;
  propertyUnits: number | null;
  occupancy: { month: string; occupied_units: number; vacant_units: number }[];
}) {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState("");
  const [occupied, setOccupied] = useState<number | "">("");
  const [vacant, setVacant] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      upsertOccupancy({
        property_id: propertyId, month,
        occupied_units: Number(occupied) || 0, vacant_units: Number(vacant) || 0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["property-occupancy", propertyId] });
      setMonth(""); setOccupied(""); setVacant(""); setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="space-y-4">
      <Surface className="p-4">
        <div className="mb-3 text-section-title">Add occupancy for a month</div>
        <div className="grid grid-cols-4 gap-3">
          <div>
            <div className="text-label mb-1">Month (YYYY-MM)</div>
            <Input value={month} onChange={(e) => setMonth(e.target.value)} placeholder="2026-04" />
          </div>
          <div>
            <div className="text-label mb-1">Occupied units</div>
            <Input type="number" value={occupied} onChange={(e) => setOccupied(e.target.value ? Number(e.target.value) : "")} />
          </div>
          <div>
            <div className="text-label mb-1">Vacant units</div>
            <Input type="number" value={vacant} onChange={(e) => setVacant(e.target.value ? Number(e.target.value) : "")} />
          </div>
          <div className="flex items-end">
            <Button variant="primary" size="sm" disabled={!month || mutation.isPending} onClick={() => mutation.mutate()}>
              Save
            </Button>
          </div>
        </div>
        {propertyUnits && <div className="mt-2 text-metadata">Total units on file: {propertyUnits}</div>}
        {error && <div className="mt-2 text-[12.5px] text-[var(--color-critical)]">{error}</div>}
      </Surface>

      <Surface>
        <SurfaceHeader title="Occupancy history" />
        {occupancy.length === 0 ? (
          <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">No occupancy data yet.</div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                <th className="px-4 py-2 font-medium">Month</th>
                <th className="px-2 py-2 font-medium text-right">Occupied</th>
                <th className="px-2 py-2 font-medium text-right">Vacant</th>
              </tr>
            </thead>
            <tbody>
              {[...occupancy].reverse().map((o) => (
                <tr key={o.month} className="border-b border-[var(--color-hairline)] last:border-0">
                  <td className="px-4 py-2.5">{formatDate(o.month)}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{o.occupied_units}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{o.vacant_units}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Surface>
    </div>
  );
}

// --------------------------------------------------------- Findings & Actions
function FindingsActionsTab({ propertyId }: { propertyId: number }) {
  const { data: findings } = useQuery({ queryKey: ["findings"], queryFn: () => listFindings() });
  const { data: actions } = useQuery({ queryKey: ["actions"], queryFn: () => listActions() });

  const propertyFindings = (findings || []).filter((f) => f.property_id === propertyId);
  const propertyActions = (actions || []).filter((a) => a.property_id === propertyId);

  return (
    <div className="space-y-4">
      <Surface>
        <SurfaceHeader title="Findings" />
        {propertyFindings.length === 0 ? (
          <div className="p-8 text-center text-[13px] text-[var(--color-ink-faint)]">No findings for this property yet.</div>
        ) : (
          <ul className="divide-y divide-[var(--color-hairline)]">
            {propertyFindings.map((f) => (
              <li key={f.id} className="px-4 py-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[13px] font-medium">{f.description}</span>
                  <StatusPill label={f.status} />
                </div>
                <div className="text-metadata">{formatCurrency(f.observed_excess)}/yr est. · {f.severity} severity</div>
              </li>
            ))}
          </ul>
        )}
      </Surface>

      <Surface>
        <SurfaceHeader title="Actions" />
        {propertyActions.length === 0 ? (
          <div className="p-8 text-center text-[13px] text-[var(--color-ink-faint)]">No actions for this property yet.</div>
        ) : (
          <ul className="divide-y divide-[var(--color-hairline)]">
            {propertyActions.map((a) => (
              <li key={a.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <div className="text-[13px] font-medium">{a.action_taken}</div>
                  <div className="text-metadata">{a.owner || "Unassigned"} · Due {a.due_date || "—"}</div>
                </div>
                <StatusPill label={a.status} />
              </li>
            ))}
          </ul>
        )}
      </Surface>
    </div>
  );
}
