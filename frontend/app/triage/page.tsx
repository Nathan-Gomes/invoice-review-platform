"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listIncidents, dismissIncident, confirmIncident, createActionForFinding,
  listProperties, type IncidentOut,
} from "@/lib/api";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { StatusPill, ConfidenceDots } from "@/components/ui/status-pill";
import { formatCurrency, formatDate, humanizeRule } from "@/lib/utils";
import { X, Search } from "lucide-react";

const TIERS = ["All", "Critical", "Watch", "Informational"];
type SortKey = "impact" | "recency" | "confidence";

function getOperatorName(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("operatorName") || "";
}

export default function TriagePage() {
  const [tier, setTier] = useState("All");
  const [propertyFilter, setPropertyFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("impact");
  const [selected, setSelected] = useState<IncidentOut | null>(null);

  const queryClient = useQueryClient();

  const { data: incidents, isLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => listIncidents(),
  });
  const { data: properties } = useQuery({ queryKey: ["properties"], queryFn: listProperties });

  const filtered = useMemo(() => {
    let rows = incidents || [];
    if (tier !== "All") rows = rows.filter((i) => i.tier === tier);
    if (propertyFilter) rows = rows.filter((i) => String(i.property_id) === propertyFilter);
    if (categoryFilter) rows = rows.filter((i) => i.category === categoryFilter);
    if (search) {
      const s = search.toLowerCase();
      rows = rows.filter(
        (i) => i.property_name.toLowerCase().includes(s) || i.messages.join(" ").toLowerCase().includes(s)
      );
    }
    const sorted = [...rows];
    if (sortKey === "impact") sorted.sort((a, b) => b.annualized_impact - a.annualized_impact);
    else if (sortKey === "recency") sorted.sort((a, b) => (a.latest_month < b.latest_month ? 1 : -1));
    else if (sortKey === "confidence") {
      const order: Record<string, number> = { Strong: 3, Likely: 2, Possible: 1 };
      sorted.sort((a, b) => (order[b.confidence] || 0) - (order[a.confidence] || 0));
    }
    return sorted;
  }, [incidents, tier, propertyFilter, categoryFilter, search, sortKey]);

  const dismissMutation = useMutation({
    mutationFn: (payload: { incident: IncidentOut; reason: string }) =>
      dismissIncident({
        property_id: payload.incident.property_id, category: payload.incident.category,
        rules: payload.incident.rules, reason: payload.reason,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setSelected(null);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (payload: { incident: IncidentOut; action?: string; status: string }) =>
      confirmIncident({
        property_id: payload.incident.property_id, category: payload.incident.category,
        rules: payload.incident.rules, recommended_action: payload.action, set_status: payload.status,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["findings"] });
      setSelected(null);
    },
  });

  const categories = Array.from(new Set((incidents || []).map((i) => i.category)));

  return (
    <div className="flex h-full">
      <div className={`flex-1 overflow-y-auto p-6 ${selected ? "max-w-[calc(100%-380px)]" : ""}`}>
        <h1 className="text-page-title mb-4">Triage</h1>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="flex gap-1 rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)] p-1">
            {TIERS.map((t) => (
              <button
                key={t}
                onClick={() => setTier(t)}
                className={`rounded-sm px-2.5 py-1 text-[12.5px] font-medium transition-colors ${
                  tier === t
                    ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                    : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)]"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <Select value={propertyFilter} onChange={(e) => setPropertyFilter(e.target.value)} className="w-44">
            <option value="">All properties</option>
            {(properties || []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </Select>

          <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="w-40">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>

          <Select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="w-44">
            <option value="impact">Sort: Impact</option>
            <option value="recency">Sort: Recency</option>
            <option value="confidence">Sort: Confidence</option>
          </Select>

          <div className="relative w-56">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-ink-faint)]" />
            <Input placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
          </div>
        </div>

        <Surface>
          {isLoading ? (
            <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">
              No incidents match this filter.
            </div>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                  <th className="px-3 py-2 font-medium">Priority</th>
                  <th className="px-2 py-2 font-medium">Property</th>
                  <th className="px-2 py-2 font-medium">Category</th>
                  <th className="px-2 py-2 font-medium">Issue</th>
                  <th className="px-2 py-2 font-medium">Cause</th>
                  <th className="px-2 py-2 font-medium">Latest month</th>
                  <th className="px-2 py-2 font-medium text-right">Est. impact</th>
                  <th className="px-2 py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((inc, i) => (
                  <tr
                    key={i}
                    onClick={() => setSelected(inc)}
                    className={`cursor-pointer border-b border-[var(--color-hairline)] last:border-0 hover:bg-[var(--color-surface-muted)] ${
                      selected === inc ? "bg-[var(--color-brand-soft)]" : ""
                    }`}
                  >
                    <td className="px-3 py-2.5"><StatusPill label={inc.tier} /></td>
                    <td className="px-2 py-2.5 font-medium">{inc.property_name}</td>
                    <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{inc.category}</td>
                    <td className="max-w-[280px] truncate px-2 py-2.5 text-[var(--color-ink-muted)]" title={inc.messages[0]}>
                      {inc.messages[0]}
                    </td>
                    <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{inc.cause}</td>
                    <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{formatDate(inc.latest_month)}</td>
                    <td className="px-2 py-2.5 text-right font-medium tabular-nums">{formatCurrency(inc.annualized_impact)}</td>
                    <td className="px-2 py-2.5"><ConfidenceDots confidence={inc.confidence} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Surface>
      </div>

      {selected && (
        <IncidentDetailPanel
          incident={selected}
          onClose={() => setSelected(null)}
          onDismiss={(reason) => dismissMutation.mutate({ incident: selected, reason })}
          onConfirm={() => confirmMutation.mutate({ incident: selected, status: "Reviewing" })}
          onInvestigate={() =>
            confirmMutation.mutate({
              incident: selected, status: "Reviewing",
              action: "Under investigation — cause not yet confirmed.",
            })
          }
          onCreateAction={async (owner, dueDate, expectedSavings, notes) => {
            const result = await confirmIncident({
              property_id: selected.property_id, category: selected.category,
              rules: selected.rules, set_status: "Pending",
            });
            await createActionForFinding(result.finding_id, {
              action_taken: `Follow up on ${selected.category} at ${selected.property_name}`,
              owner, due_date: dueDate, expected_savings: expectedSavings, notes,
            });
            queryClient.invalidateQueries({ queryKey: ["incidents"] });
            queryClient.invalidateQueries({ queryKey: ["findings"] });
            queryClient.invalidateQueries({ queryKey: ["actions"] });
            setSelected(null);
          }}
        />
      )}
    </div>
  );
}

function IncidentDetailPanel({
  incident,
  onClose,
  onDismiss,
  onConfirm,
  onInvestigate,
  onCreateAction,
}: {
  incident: IncidentOut;
  onClose: () => void;
  onDismiss: (reason: string) => void;
  onConfirm: () => void;
  onInvestigate: () => void;
  onCreateAction: (owner: string, dueDate: string, expectedSavings: number | null, notes: string) => void;
}) {
  const [showDismissForm, setShowDismissForm] = useState(false);
  const [dismissReason, setDismissReason] = useState("");
  const [showActionForm, setShowActionForm] = useState(false);
  const [owner, setOwner] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [expectedSavings, setExpectedSavings] = useState<number | null>(incident.annualized_impact);
  const [notes, setNotes] = useState("");

  return (
    <aside className="flex w-[380px] shrink-0 flex-col border-l border-[var(--color-hairline)] bg-[var(--color-surface)]">
      <div className="flex items-center justify-between border-b border-[var(--color-hairline)] px-4 py-3">
        <div>
          <div className="text-[14px] font-semibold">{incident.property_name}</div>
          <div className="text-metadata">{incident.category}</div>
        </div>
        <button onClick={onClose} className="text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mb-3 flex items-center gap-2">
          <StatusPill label={incident.tier} />
          <span className="text-[12px] text-[var(--color-ink-muted)]">
            {incident.severity} severity · {incident.confidence} confidence
          </span>
        </div>

        {incident.explanation && (
          <p className="mb-4 text-[13px] leading-relaxed text-[var(--color-ink)]">{incident.explanation}</p>
        )}

        <div className="mb-4 grid grid-cols-2 gap-3">
          <div>
            <div className="text-label">Estimated annual impact</div>
            <div className="text-[18px] font-semibold tabular-nums">{formatCurrency(incident.annualized_impact)}</div>
          </div>
          <div>
            <div className="text-label">Cause</div>
            <div className="text-[14px] font-medium">{incident.cause}</div>
          </div>
        </div>

        <div className="mb-4">
          <div className="text-label mb-1">Months involved</div>
          <div className="flex flex-wrap gap-1">
            {incident.months.map((m) => (
              <span key={m} className="rounded-sm bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[11.5px] text-[var(--color-ink-muted)]">
                {formatDate(m)}
              </span>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-label mb-1">Signals detected</div>
          <ul className="space-y-1">
            {incident.rules.map((r) => (
              <li key={r} className="text-[12.5px] text-[var(--color-ink-muted)]">
                • {humanizeRule(r)}
              </li>
            ))}
          </ul>
        </div>

        <div className="mb-4">
          <div className="text-label mb-1">Evidence</div>
          <ul className="space-y-1.5">
            {incident.messages.map((m, i) => (
              <li key={i} className="text-[12.5px] leading-relaxed text-[var(--color-ink-muted)]">
                {m}
              </li>
            ))}
          </ul>
        </div>

        {showDismissForm && (
          <div className="mb-4 rounded-md border border-[var(--color-hairline)] p-3">
            <div className="text-label mb-1">Reason for dismissing</div>
            <Input value={dismissReason} onChange={(e) => setDismissReason(e.target.value)} className="mb-2" />
            <Button variant="secondary" size="sm" onClick={() => onDismiss(dismissReason)}>
              Confirm dismissal
            </Button>
          </div>
        )}

        {showActionForm && (
          <div className="mb-4 space-y-2 rounded-md border border-[var(--color-hairline)] p-3">
            <div>
              <div className="text-label mb-1">Owner</div>
              <Input value={owner} onChange={(e) => setOwner(e.target.value)} />
            </div>
            <div>
              <div className="text-label mb-1">Due date</div>
              <Input placeholder="YYYY-MM-DD" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </div>
            <div>
              <div className="text-label mb-1">Expected annual savings</div>
              <Input
                type="number"
                value={expectedSavings ?? ""}
                onChange={(e) => setExpectedSavings(e.target.value ? Number(e.target.value) : null)}
              />
            </div>
            <div>
              <div className="text-label mb-1">Notes</div>
              <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => onCreateAction(owner, dueDate, expectedSavings, notes)}
            >
              Create finding + action
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 border-t border-[var(--color-hairline)] px-4 py-3">
        <Button variant="danger" size="sm" onClick={() => setShowDismissForm((v) => !v)}>
          Dismiss
        </Button>
        <Button variant="secondary" size="sm" onClick={onInvestigate}>
          Investigate
        </Button>
        <Button variant="secondary" size="sm" onClick={onConfirm}>
          Confirm finding
        </Button>
        <Button variant="primary" size="sm" onClick={() => setShowActionForm((v) => !v)}>
          Create action
        </Button>
      </div>
    </aside>
  );
}
