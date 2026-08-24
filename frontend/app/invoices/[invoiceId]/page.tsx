"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronLeft, ChevronRight, ArrowLeft, AlertTriangle, Copy } from "lucide-react";
import {
  getInvoice, getInvoiceDocumentUrl, updateInvoice, approveInvoice, listInvoices,
  listProperties, getInvoiceAudit, type InvoiceUpdatePayload,
} from "@/lib/api";
import { Surface } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { StickyActionBar } from "@/components/ui/sticky-action-bar";
import { StatusPill } from "@/components/ui/status-pill";
import { FieldGroup, FieldWrapper } from "@/components/features/invoice-field-group";
import { formatCurrency, formatDate } from "@/lib/utils";

const CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"];

function getOperatorName(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("operatorName") || "";
}

export default function InvoiceReviewPage() {
  const params = useParams<{ invoiceId: string }>();
  const invoiceId = Number(params.invoiceId);
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: invoice, isLoading } = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () => getInvoice(invoiceId),
  });
  const { data: properties } = useQuery({ queryKey: ["properties"], queryFn: listProperties });
  const { data: queueList } = useQuery({ queryKey: ["invoices", "All", ""], queryFn: () => listInvoices({}) });
  const { data: matchedInvoice } = useQuery({
    queryKey: ["invoice", invoice?.duplicate.matched_invoice_id],
    queryFn: () => getInvoice(invoice!.duplicate.matched_invoice_id!),
    enabled: !!invoice?.duplicate.matched_invoice_id,
  });
  const { data: auditLog } = useQuery({
    queryKey: ["invoice-audit", invoiceId],
    queryFn: () => getInvoiceAudit(invoiceId),
  });

  const [form, setForm] = useState<InvoiceUpdatePayload | null>(null);
  const [overrideDuplicate, setOverrideDuplicate] = useState(false);

  useEffect(() => {
    if (invoice) {
      setForm({
        property_id: invoice.property_id,
        category: invoice.category,
        vendor: invoice.vendor,
        invoice_number: invoice.invoice_number || "",
        billing_start: invoice.billing_start || "",
        billing_end: invoice.billing_end || "",
        consumption: invoice.consumption,
        consumption_unit: invoice.consumption_unit || "",
        taxes_fees: invoice.taxes_fees,
        total_cost: invoice.total_cost,
        notes: invoice.notes || "",
        duplicate_override: false,
        changed_by: getOperatorName() || "unknown",
      });
      setOverrideDuplicate(false);
    }
  }, [invoice]);

  const saveMutation = useMutation({
    mutationFn: (payload: InvoiceUpdatePayload) => updateInvoice(invoiceId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice", invoiceId] });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveInvoice(invoiceId, getOperatorName() || "unknown"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice", invoiceId] });
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      goToNext();
    },
  });

  const pdfInvoices = queueList || [];
  const currentIndex = pdfInvoices.findIndex((i) => i.id === invoiceId);
  const prevId = currentIndex > 0 ? pdfInvoices[currentIndex - 1].id : null;
  const nextId = currentIndex >= 0 && currentIndex < pdfInvoices.length - 1 ? pdfInvoices[currentIndex + 1].id : null;

  function goToNext() {
    if (nextId) router.push(`/invoices/${nextId}`);
    else router.push("/invoices");
  }

  if (isLoading || !invoice || !form) {
    return (
      <div className="mx-auto max-w-[1400px] p-6">
        <div className="h-8 w-48 animate-pulse rounded-md bg-[var(--color-hairline)]" />
      </div>
    );
  }

  const confidence = invoice.field_confidence || {};
  const errors = invoice.validation_errors || [];
  const canApprove = errors.length === 0 && (!invoice.duplicate.is_duplicate || overrideDuplicate);

  function updateField<K extends keyof InvoiceUpdatePayload>(key: K, value: InvoiceUpdatePayload[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function handleSave() {
    if (!form) return;
    saveMutation.mutate({ ...form, duplicate_override: overrideDuplicate, changed_by: getOperatorName() || "unknown" });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-hairline)] bg-[var(--color-surface)] px-6 py-3">
        <div className="flex items-center gap-3">
          <Link href="/invoices" className="text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]">
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="text-[14px] font-semibold">{invoice.filename}</div>
            <div className="text-metadata">Invoice #{invoice.id}</div>
          </div>
          <StatusPill label={invoice.state} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-metadata">
            {currentIndex >= 0 ? `${currentIndex + 1} of ${pdfInvoices.length}` : ""}
          </span>
          <Button variant="ghost" size="sm" disabled={!prevId} onClick={() => prevId && router.push(`/invoices/${prevId}`)}>
            <ChevronLeft size={15} /> Previous
          </Button>
          <Button variant="ghost" size="sm" disabled={!nextId} onClick={() => nextId && router.push(`/invoices/${nextId}`)}>
            Next <ChevronRight size={15} />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: PDF viewer */}
        <div className="flex-1 border-r border-[var(--color-hairline)] bg-[var(--color-surface-muted)] p-4">
          {invoice.has_pdf ? (
            <iframe
              src={getInvoiceDocumentUrl(invoice.id)}
              className="h-full w-full rounded-md border border-[var(--color-hairline)] bg-white"
              title="Invoice PDF"
            />
          ) : (
            <div className="h-full overflow-auto rounded-md border border-[var(--color-hairline)] bg-white p-4">
              <div className="text-label mb-2">No PDF preview — raw extracted text</div>
              <pre className="whitespace-pre-wrap text-[12.5px] text-[var(--color-ink-muted)]">{invoice.raw_text}</pre>
            </div>
          )}
        </div>

        {/* Right: fields */}
        <div className="flex w-[420px] shrink-0 flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {errors.length > 0 && (
              <div className="mb-4 rounded-md border border-[var(--color-critical)]/25 bg-[var(--color-critical-soft)] px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-critical)]">
                  <AlertTriangle size={14} /> Cannot approve yet
                </div>
                <ul className="mt-1 list-disc pl-5 text-[12.5px] text-[var(--color-critical)]">
                  {errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}

            {invoice.duplicate.is_duplicate && (
              <div className="mb-4 rounded-md border border-[var(--color-watch)]/25 bg-[var(--color-watch-soft)] px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-watch)]">
                  <Copy size={14} /> Possible duplicate
                </div>
                <div className="mt-1 text-[12.5px] text-[var(--color-ink-muted)]">{invoice.duplicate.reason}</div>
                {matchedInvoice && (
                  <div className="mt-2 grid grid-cols-2 gap-2 rounded-md bg-white/60 p-2 text-[12px]">
                    <div>
                      <div className="text-metadata">This invoice</div>
                      <div>{invoice.vendor}</div>
                      <div>{formatDate(invoice.billing_start)} – {formatDate(invoice.billing_end)}</div>
                      <div className="font-medium">{formatCurrency(invoice.total_cost)}</div>
                    </div>
                    <div>
                      <div className="text-metadata">Invoice #{matchedInvoice.id}</div>
                      <div>{matchedInvoice.vendor}</div>
                      <div>{formatDate(matchedInvoice.billing_start)} – {formatDate(matchedInvoice.billing_end)}</div>
                      <div className="font-medium">{formatCurrency(matchedInvoice.total_cost)}</div>
                    </div>
                  </div>
                )}
                <label className="mt-2 flex items-center gap-2 text-[12.5px]">
                  <input
                    type="checkbox"
                    checked={overrideDuplicate}
                    onChange={(e) => setOverrideDuplicate(e.target.checked)}
                    className="h-3.5 w-3.5 accent-[var(--color-brand)]"
                  />
                  This is not a duplicate — allow approval
                </label>
              </div>
            )}

            <FieldGroup title="Invoice">
              <FieldWrapper label="Property" fullWidth>
                <Select
                  value={form.property_id ?? ""}
                  onChange={(e) => updateField("property_id", e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">(unassigned)</option>
                  {(properties || []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </Select>
              </FieldWrapper>
              <FieldWrapper label="Category" confidence={confidence.category}>
                <Select value={form.category} onChange={(e) => updateField("category", e.target.value)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </FieldWrapper>
              <FieldWrapper label="Vendor" confidence={confidence.vendor}>
                <Input value={form.vendor} onChange={(e) => updateField("vendor", e.target.value)} />
              </FieldWrapper>
              <FieldWrapper label="Invoice number" confidence={confidence.invoice_number} fullWidth>
                <Input value={form.invoice_number} onChange={(e) => updateField("invoice_number", e.target.value)} />
              </FieldWrapper>
            </FieldGroup>

            <FieldGroup title="Billing Period">
              <FieldWrapper label="Start" confidence={confidence.billing_start}>
                <Input
                  placeholder="YYYY-MM-DD"
                  value={form.billing_start}
                  onChange={(e) => updateField("billing_start", e.target.value)}
                />
              </FieldWrapper>
              <FieldWrapper label="End" confidence={confidence.billing_end}>
                <Input
                  placeholder="YYYY-MM-DD"
                  value={form.billing_end}
                  onChange={(e) => updateField("billing_end", e.target.value)}
                />
              </FieldWrapper>
            </FieldGroup>

            <FieldGroup title="Usage">
              <FieldWrapper label="Consumption" confidence={confidence.consumption}>
                <Input
                  type="number"
                  value={form.consumption ?? ""}
                  onChange={(e) => updateField("consumption", e.target.value ? Number(e.target.value) : null)}
                />
              </FieldWrapper>
              <FieldWrapper label="Unit" confidence={confidence.consumption_unit}>
                <Input value={form.consumption_unit} onChange={(e) => updateField("consumption_unit", e.target.value)} />
              </FieldWrapper>
            </FieldGroup>

            <FieldGroup title="Amount">
              <FieldWrapper label="Taxes / fees">
                <Input
                  type="number"
                  value={form.taxes_fees ?? ""}
                  onChange={(e) => updateField("taxes_fees", e.target.value ? Number(e.target.value) : null)}
                />
              </FieldWrapper>
              <FieldWrapper label="Total cost" confidence={confidence.total_cost}>
                <Input
                  type="number"
                  value={form.total_cost ?? ""}
                  onChange={(e) => updateField("total_cost", e.target.value ? Number(e.target.value) : null)}
                />
              </FieldWrapper>
              <FieldWrapper label="Notes" fullWidth>
                <Textarea rows={2} value={form.notes} onChange={(e) => updateField("notes", e.target.value)} />
              </FieldWrapper>
            </FieldGroup>

            {auditLog && auditLog.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-label">Change history ({auditLog.length})</summary>
                <ul className="mt-2 space-y-1.5 text-[12px] text-[var(--color-ink-muted)]">
                  {auditLog.map((e) => (
                    <li key={e.id}>
                      {e.changed_by || "unknown"} changed <b>{e.field}</b>: {e.old_value} → {e.new_value}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <StickyActionBar>
            <Button variant="secondary" size="sm" onClick={handleSave} disabled={saveMutation.isPending}>
              Save corrections
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!canApprove || approveMutation.isPending}
              title={!canApprove ? "Resolve validation errors or override the duplicate flag first" : undefined}
              onClick={() => {
                saveMutation.mutate(
                  { ...form, duplicate_override: overrideDuplicate, changed_by: getOperatorName() || "unknown" },
                  { onSuccess: () => approveMutation.mutate() }
                );
              }}
            >
              Approve invoice
            </Button>
          </StickyActionBar>
        </div>
      </div>
    </div>
  );
}
