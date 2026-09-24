"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Upload, Search, CheckCircle2 } from "lucide-react";
import { listInvoices, uploadInvoices, batchApprove, type InvoiceSummary } from "@/lib/api";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import { formatCurrency, formatDate } from "@/lib/utils";

const STATES = ["All", "Needs Review", "Problem", "Duplicate", "Approved", "Rejected"];

function getOperatorName(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("operatorName") || "";
}

export default function InvoicesPage() {
  const [state, setState] = useState("All");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const { data: invoices, isLoading } = useQuery({
    queryKey: ["invoices", state, search],
    queryFn: () => listInvoices({ state: state === "All" ? undefined : state, search: search || undefined }),
  });

  const uploadMutation = useMutation({
    mutationFn: uploadInvoices,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const batchApproveMutation = useMutation({
    mutationFn: () => batchApprove(Array.from(selected), getOperatorName() || "unknown"),
    onSuccess: () => {
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
  });

  const cleanHighConfidence = (invoices || []).filter((inv) => inv.high_confidence);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllClean() {
    setSelected(new Set(cleanHighConfidence.map((i) => i.id)));
  }

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-page-title">Invoices</h1>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              if (files.length) uploadMutation.mutate(files);
              e.target.value = "";
            }}
          />
          <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload size={14} />
            Upload
          </Button>
        </div>
      </div>

      {uploadMutation.isPending && (
        <div className="mb-4 rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)] px-4 py-2 text-[13px] text-[var(--color-ink-muted)]">
          Uploading and extracting fields…
        </div>
      )}
      {uploadMutation.isSuccess && (
        <div className="mb-4 rounded-md border border-[var(--color-good)]/30 bg-[var(--color-good-soft)] px-4 py-2 text-[13px] text-[var(--color-good)]">
          {uploadMutation.data.length} file(s) processed.{" "}
          {uploadMutation.data.filter((r) => r.status === "duplicate_skipped").length > 0 &&
            `${uploadMutation.data.filter((r) => r.status === "duplicate_skipped").length} skipped as duplicates.`}
        </div>
      )}

      <div className="mb-4 flex items-center gap-3">
        <div className="flex gap-1 rounded-md border border-[var(--color-hairline)] bg-[var(--color-surface)] p-1">
          {STATES.map((s) => (
            <button
              key={s}
              onClick={() => setState(s)}
              className={`rounded-sm px-2.5 py-1 text-[12.5px] font-medium transition-colors ${
                state === s
                  ? "bg-[var(--color-brand-soft)] text-[var(--color-brand)]"
                  : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="relative w-64">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-ink-faint)]" />
          <Input
            placeholder="Search filename, vendor, invoice #"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      {cleanHighConfidence.length > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-md border border-[var(--color-brand)]/25 bg-[var(--color-brand-soft)] px-4 py-2.5">
          <div className="flex items-center gap-2 text-[13px] text-[var(--color-ink)]">
            <CheckCircle2 size={15} className="text-[var(--color-brand)]" />
            {cleanHighConfidence.length} invoice(s) in this view are high-confidence with no validation problems.
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={selectAllClean}>
              Select all clean
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={selected.size === 0 || batchApproveMutation.isPending}
              onClick={() => batchApproveMutation.mutate()}
            >
              Batch approve {selected.size > 0 ? `(${selected.size})` : ""}
            </Button>
          </div>
        </div>
      )}

      <Surface>
        {isLoading ? (
          <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
        ) : !invoices || invoices.length === 0 ? (
          <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">
            No invoices match this filter. Upload a PDF or accounting export to get started.
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                <th className="w-8 px-4 py-2" />
                <th className="px-2 py-2 font-medium">Filename</th>
                <th className="px-2 py-2 font-medium">Property</th>
                <th className="px-2 py-2 font-medium">Vendor</th>
                <th className="px-2 py-2 font-medium">Billing period</th>
                <th className="px-2 py-2 font-medium text-right">Total</th>
                <th className="px-2 py-2 font-medium">State</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv: InvoiceSummary) => (
                <tr key={inv.id} className="border-b border-[var(--color-hairline)] last:border-0 hover:bg-[var(--color-surface-muted)]">
                  <td className="px-4 py-2.5">
                    {inv.high_confidence && (
                      <input
                        type="checkbox"
                        checked={selected.has(inv.id)}
                        onChange={() => toggleSelect(inv.id)}
                        className="h-3.5 w-3.5 rounded-sm accent-[var(--color-brand)]"
                      />
                    )}
                  </td>
                  <td className="px-2 py-2.5">
                    <Link href={`/invoices/${inv.id}`} className="font-medium text-[var(--color-ink)] hover:text-[var(--color-brand)]">
                      {inv.filename}
                    </Link>
                  </td>
                  <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{inv.property_name || "—"}</td>
                  <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{inv.vendor || "—"}</td>
                  <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">
                    {formatDate(inv.billing_start)} – {formatDate(inv.billing_end)}
                  </td>
                  <td className="px-2 py-2.5 text-right font-medium tabular-nums">{formatCurrency(inv.total_cost)}</td>
                  <td className="px-2 py-2.5"><StatusPill label={inv.state} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Surface>
    </div>
  );
}
