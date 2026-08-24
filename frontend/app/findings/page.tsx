"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listFindings, updateFindingStatus, listActions, updateAction,
  createActionForFinding, type FindingOut, type ActionOut,
} from "@/lib/api";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import { formatCurrency } from "@/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";

const FINDING_STATUSES = ["New", "Reviewing", "Pending", "Recovered", "Closed", "Dismissed"];
const ACTION_STATUSES = ["New", "Investigating", "Actioned", "Resolved"];

export default function FindingsActionsPage() {
  const [tab, setTab] = useState<"Findings" | "Actions">("Findings");

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <h1 className="text-page-title mb-4">Findings & Actions</h1>
      <div className="mb-4 flex gap-1 rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)] p-1 w-fit">
        {(["Findings", "Actions"] as const).map((t) => (
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
      {tab === "Findings" ? <FindingsList /> : <ActionsList />}
    </div>
  );
}

function FindingsList() {
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const { data: findings, isLoading } = useQuery({
    queryKey: ["findings", statusFilter],
    queryFn: () => listFindings(statusFilter || undefined),
  });

  return (
    <Surface>
      <SurfaceHeader
        title="Findings"
        action={
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
            <option value="">All statuses</option>
            {FINDING_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        }
      />
      {isLoading ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
      ) : !findings || findings.length === 0 ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">
          No findings yet — confirm or investigate an incident from Triage.
        </div>
      ) : (
        <ul className="divide-y divide-[var(--color-hairline)]">
          {findings.map((f) => (
            <FindingRow
              key={f.id}
              finding={f}
              expanded={expanded === f.id}
              onToggle={() => setExpanded(expanded === f.id ? null : f.id)}
              onChanged={() => queryClient.invalidateQueries({ queryKey: ["findings"] })}
            />
          ))}
        </ul>
      )}
    </Surface>
  );
}

function FindingRow({
  finding,
  expanded,
  onToggle,
  onChanged,
}: {
  finding: FindingOut;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const [status, setStatus] = useState(finding.status);
  const [dismissReason, setDismissReason] = useState("");
  const [showActionForm, setShowActionForm] = useState(false);
  const [owner, setOwner] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [expectedSavings, setExpectedSavings] = useState<number | null>(finding.observed_excess);
  const [notes, setNotes] = useState("");

  const statusMutation = useMutation({
    mutationFn: () => updateFindingStatus(finding.id, status, status === "Dismissed" ? dismissReason : undefined),
    onSuccess: onChanged,
  });
  const actionMutation = useMutation({
    mutationFn: () =>
      createActionForFinding(finding.id, {
        action_taken: finding.recommended_action, owner, due_date: dueDate,
        expected_savings: expectedSavings, notes,
      }),
    onSuccess: () => {
      setShowActionForm(false);
      onChanged();
    },
  });

  return (
    <li className="px-4 py-3">
      <button onClick={onToggle} className="flex w-full items-center justify-between text-left">
        <div className="flex items-center gap-2">
          <StatusPill label={finding.status} />
          <span className="text-[13.5px] font-medium">{finding.description}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="tabular-nums text-[13px] font-medium">{formatCurrency(finding.observed_excess)}/yr</span>
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-[var(--color-hairline)] pt-3 text-[13px]">
          <div>
            <span className="text-label">Property: </span>{finding.property_name} · <span className="text-label">Category: </span>{finding.category}
          </div>
          <div>
            <div className="text-label mb-1">Evidence</div>
            <p className="text-[var(--color-ink-muted)]">{finding.evidence}</p>
          </div>
          <div>
            <div className="text-label mb-1">Recommended action</div>
            <p className="text-[var(--color-ink-muted)]">{finding.recommended_action}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-label">Severity:</span> {finding.severity}
            <span className="text-label ml-3">Confidence:</span> {finding.confidence}
            <span className="text-label ml-3">Cause:</span> {finding.cause}
          </div>

          <div className="flex items-center gap-2">
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
              {FINDING_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
            {status === "Dismissed" && (
              <Input placeholder="Reason for dismissing" value={dismissReason} onChange={(e) => setDismissReason(e.target.value)} className="w-56" />
            )}
            <Button variant="secondary" size="sm" onClick={() => statusMutation.mutate()} disabled={statusMutation.isPending}>
              Save status
            </Button>
            <Button variant="primary" size="sm" onClick={() => setShowActionForm((v) => !v)}>
              Add action
            </Button>
          </div>

          {showActionForm && (
            <div className="grid grid-cols-4 gap-2 rounded-md border border-[var(--color-hairline)] p-3">
              <div>
                <div className="text-label mb-1">Owner</div>
                <Input value={owner} onChange={(e) => setOwner(e.target.value)} />
              </div>
              <div>
                <div className="text-label mb-1">Due date</div>
                <Input placeholder="YYYY-MM-DD" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
              </div>
              <div>
                <div className="text-label mb-1">Expected savings</div>
                <Input
                  type="number"
                  value={expectedSavings ?? ""}
                  onChange={(e) => setExpectedSavings(e.target.value ? Number(e.target.value) : null)}
                />
              </div>
              <div className="flex items-end">
                <Button variant="primary" size="sm" onClick={() => actionMutation.mutate()} disabled={actionMutation.isPending}>
                  Create action
                </Button>
              </div>
              <div className="col-span-4">
                <div className="text-label mb-1">Notes</div>
                <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function ActionsList() {
  const [statusFilter, setStatusFilter] = useState("");
  const queryClient = useQueryClient();

  const { data: actions, isLoading } = useQuery({ queryKey: ["actions"], queryFn: () => listActions() });
  const filtered = (actions || []).filter((a) => !statusFilter || a.status === statusFilter);

  return (
    <Surface>
      <SurfaceHeader
        title="Actions"
        action={
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
            <option value="">All statuses</option>
            {ACTION_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        }
      />
      {isLoading ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">
          No actions yet — create one from a finding or from Triage.
        </div>
      ) : (
        <ul className="divide-y divide-[var(--color-hairline)]">
          {filtered.map((a) => (
            <ActionRow key={a.id} action={a} onChanged={() => queryClient.invalidateQueries({ queryKey: ["actions"] })} />
          ))}
        </ul>
      )}
    </Surface>
  );
}

function ActionRow({ action, onChanged }: { action: ActionOut; onChanged: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState(action.status);
  const [confirmedSavings, setConfirmedSavings] = useState<number | null>(action.confirmed_savings);
  const [notes, setNotes] = useState(action.notes || "");

  const mutation = useMutation({
    mutationFn: () => updateAction(action.id, { status, confirmed_savings: confirmedSavings ?? undefined, notes }),
    onSuccess: onChanged,
  });

  return (
    <li className="px-4 py-3">
      <button onClick={() => setExpanded((v) => !v)} className="flex w-full items-center justify-between text-left">
        <div>
          <div className="text-[13.5px] font-medium">{action.action_taken}</div>
          <div className="text-metadata">{action.property_name} · {action.owner || "Unassigned"} · Due {action.due_date || "—"}</div>
        </div>
        <div className="flex items-center gap-3">
          <StatusPill label={action.status} />
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-[var(--color-hairline)] pt-3 text-[13px]">
          <div>
            <span className="text-label">Linked finding: </span>{action.finding_description}
          </div>
          <div className="flex items-center gap-4">
            <div>
              <span className="text-label">Expected savings: </span>
              <span className="font-medium">{formatCurrency(action.expected_savings)}</span>
            </div>
            {action.confirmed_savings !== null && (
              <div>
                <span className="text-label">Confirmed savings: </span>
                <span className="font-medium">{formatCurrency(action.confirmed_savings)}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
              {ACTION_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
            <Input
              type="number"
              placeholder="Confirmed savings"
              value={confirmedSavings ?? ""}
              onChange={(e) => setConfirmedSavings(e.target.value ? Number(e.target.value) : null)}
              className="w-40"
            />
            <Input placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} className="w-56" />
            <Button variant="primary" size="sm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
              Save
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
