/**
 * lib/api.ts — thin typed wrapper around the FastAPI backend.
 * Every function here maps to one backend endpoint; no component should
 * construct a fetch URL by hand.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse failure, fall back to statusText */
    }
    throw new ApiError(res.status, detail);
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res as unknown as T;
}

// ---------------------------------------------------------------- types ----

export interface OverviewMetrics {
  total_monthly_spend: number;
  yoy_variance_pct: number | null;
  estimated_annual_excess: number;
  invoices_needing_review: number;
  open_critical_incidents: number;
  open_watch_incidents: number;
}
export interface NeedsAttentionRow {
  property_id: number;
  property_name: string;
  category: string;
  tier: string;
  severity: string;
  confidence: string;
  issue: string;
  cause: string;
  annualized_impact: number;
  latest_month: string;
}
export interface PortfolioTrendPoint { month: string; total_cost: number; }
export interface CategoryBreakdown { category: string; total_cost: number; }
export interface PropertyRanking { property_id: number; property_name: string; observed_excess: number; }
export interface RecentAction {
  id: number; property_name: string | null; action_taken: string;
  owner: string | null; status: string; due_date: string | null;
}
export interface OverviewResponse {
  metrics: OverviewMetrics;
  needs_attention: NeedsAttentionRow[];
  portfolio_trend: PortfolioTrendPoint[];
  category_breakdown: CategoryBreakdown[];
  top_properties_by_excess: PropertyRanking[];
  recent_actions: RecentAction[];
}

export interface PropertyOut {
  id: number; name: string; address: string | null; units: number | null;
  sqft: number | null; construction_year: number | null;
  heating_type: string | null; metering_type: string | null;
}
export interface CategoryMonthMetrics {
  category: string; month: string; total_cost: number;
  occupied_units: number | null; cost_per_occupied_unit: number | null;
  consumption_per_occupied_unit: number | null; usage_per_unit_per_day: number | null;
  effective_rate: number | null; yoy_variance_pct: number | null;
  expected_cost: number | null; observed_excess: number | null;
  cause: string; baseline_method: string | null; baseline_confidence: string;
  explanation: string;
}
export interface PropertyDetail {
  property: PropertyOut;
  current_month_by_category: CategoryMonthMetrics[];
  open_incident_count: number;
}
export interface TrendPoint { month: string; total_cost: number; expected_cost: number | null; invoice_id: number; }
export interface OccupancyOut {
  property_id: number; property_name: string | null; month: string;
  occupied_units: number; vacant_units: number;
}

export interface InvoiceSummary {
  id: number; filename: string; property_id: number | null; property_name: string | null;
  category: string; vendor: string; invoice_number: string | null;
  billing_start: string | null; billing_end: string | null; total_cost: number | null;
  consumption: number | null; consumption_unit: string | null; state: string;
  high_confidence: boolean; approved_by: string | null; last_modified_by: string | null;
}
export interface DuplicateInfo { is_duplicate: boolean; reason: string | null; matched_invoice_id: number | null; }
export interface InvoiceDetail {
  id: number; source_file_id: number; filename: string; filetype: string; has_pdf: boolean;
  raw_text: string | null; property_id: number | null; category: string; vendor: string;
  invoice_number: string | null; billing_start: string | null; billing_end: string | null;
  consumption: number | null; consumption_unit: string | null; taxes_fees: number | null;
  total_cost: number | null; notes: string | null; approved: boolean;
  approved_by: string | null; last_modified_by: string | null;
  field_confidence: Record<string, number>; validation_errors: string[];
  duplicate: DuplicateInfo; state: string;
}
export interface InvoiceUpdatePayload {
  property_id: number | null; category: string; vendor: string; invoice_number: string;
  billing_start: string; billing_end: string; consumption: number | null;
  consumption_unit: string; taxes_fees: number | null; total_cost: number | null;
  notes: string; duplicate_override: boolean; changed_by: string;
}
export interface AuditLogEntry {
  id: number; invoice_id: number; field: string; old_value: string | null;
  new_value: string | null; changed_by: string | null; changed_at: string;
}
export interface UploadResult {
  filename: string; status: string; invoice_id: number | null;
  source_file_id: number | null; message: string | null;
}
export interface BatchApproveResult { approved: number; skipped: number; skipped_ids: number[]; }

export interface IncidentOut {
  property_id: number; property_name: string; category: string; months: string[];
  latest_month: string; rules: string[]; severity: string; confidence: string;
  cause: string; tier: string; observed_excess_monthly: number; annualized_impact: number;
  score: number; messages: string[]; is_data_quality_only: boolean;
  explanation: string | null; primary_invoice_id: number | null;
}
export interface FindingOut {
  id: number; property_id: number | null; property_name: string | null; category: string;
  description: string; evidence: string; observed_excess: number | null;
  recommended_action: string; severity: string; confidence: string; cause: string;
  owner: string | null; status: string; source_invoice_ids: number[];
  dismissed_reason: string | null; created_at: string;
}
export interface ActionOut {
  id: number; finding_id: number; finding_description: string | null;
  property_id: number | null; property_name: string | null; action_taken: string;
  owner: string | null; due_date: string | null; status: string; notes: string | null;
  expected_savings: number | null; confirmed_savings: number | null; created_at: string | null;
}
export interface ThresholdSettings {
  threshold_yoy_pct: number; threshold_usage_pct: number; threshold_rate_pct: number;
  threshold_sustained_months: number; threshold_stddev: number;
}
export interface DismissedPatternOut {
  id: number; property_id: number; property_name: string | null; category: string;
  rule: string; reason: string | null; created_at: string;
}
export interface OccupancyImportRow {
  property_name: string; month: string; occupied_units: number; vacant_units: number;
  valid: boolean; reason: string | null;
}

// -------------------------------------------------------------- overview --
export const getOverview = () => request<OverviewResponse>("/api/overview");

// ------------------------------------------------------------ properties --
export const listProperties = () => request<PropertyOut[]>("/api/properties");
export const createProperty = (payload: Partial<PropertyOut>) =>
  request<PropertyOut>("/api/properties", { method: "POST", body: JSON.stringify(payload) });
export const getProperty = (id: number) => request<PropertyDetail>(`/api/properties/${id}`);
export const getPropertyTrend = (id: number, category: string, monthsBack = 12) =>
  request<TrendPoint[]>(`/api/properties/${id}/trend?category=${encodeURIComponent(category)}&months_back=${monthsBack}`);
export const getPropertyMonths = (id: number, category: string) =>
  request<string[]>(`/api/properties/${id}/months?category=${encodeURIComponent(category)}`);
export const getPropertyAnalysis = (id: number, category: string, month: string) =>
  request<CategoryMonthMetrics>(`/api/properties/${id}/analysis?category=${encodeURIComponent(category)}&month=${month}`);
export const getPropertyOccupancy = (id: number) =>
  request<OccupancyOut[]>(`/api/properties/${id}/occupancy`);
export const upsertOccupancy = (payload: { property_id: number; month: string; occupied_units: number; vacant_units: number }) =>
  request<{ ok: boolean }>("/api/properties/occupancy", { method: "POST", body: JSON.stringify(payload) });

// -------------------------------------------------------------- invoices --
export const listInvoices = (params?: { state?: string; property_id?: number; category?: string; search?: string }) => {
  const qs = new URLSearchParams();
  if (params?.state) qs.set("state", params.state);
  if (params?.property_id) qs.set("property_id", String(params.property_id));
  if (params?.category) qs.set("category", params.category);
  if (params?.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<InvoiceSummary[]>(`/api/invoices${suffix}`);
};
export const getInvoice = (id: number) => request<InvoiceDetail>(`/api/invoices/${id}`);
export const getInvoiceDocumentUrl = (id: number) => `${API_BASE}/api/invoices/${id}/document`;
export const getInvoiceAudit = (id: number) => request<AuditLogEntry[]>(`/api/invoices/${id}/audit`);
export const updateInvoice = (id: number, payload: InvoiceUpdatePayload) =>
  request<InvoiceDetail>(`/api/invoices/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const approveInvoice = (id: number, approvedBy: string) =>
  request<{ ok: boolean }>(`/api/invoices/${id}/approve`, { method: "POST", body: JSON.stringify({ approved_by: approvedBy }) });
export const batchApprove = (invoiceIds: number[], approvedBy: string) =>
  request<BatchApproveResult>("/api/invoices/batch-approve", {
    method: "POST", body: JSON.stringify({ invoice_ids: invoiceIds, approved_by: approvedBy }),
  });
export const uploadInvoices = async (files: File[]): Promise<UploadResult[]> => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${API_BASE}/api/invoices/upload`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json();
};

// ------------------------------------------------------------- incidents --
export const listIncidents = (params?: { tier?: string; property_id?: number; category?: string }) => {
  const qs = new URLSearchParams();
  if (params?.tier) qs.set("tier", params.tier);
  if (params?.property_id) qs.set("property_id", String(params.property_id));
  if (params?.category) qs.set("category", params.category);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<IncidentOut[]>(`/api/incidents${suffix}`);
};
export const rescanIncidents = () => request<IncidentOut[]>("/api/incidents/scan", { method: "POST" });
export const dismissIncident = (payload: { property_id: number; category: string; rules: string[]; reason: string }) =>
  request<{ ok: boolean }>("/api/incidents/dismiss", { method: "POST", body: JSON.stringify(payload) });
export const confirmIncident = (payload: {
  property_id: number; category: string; rules: string[];
  recommended_action?: string; set_status: string;
}) => request<{ ok: boolean; finding_id: number }>("/api/incidents/confirm", {
  method: "POST", body: JSON.stringify(payload),
});
export const listDismissedPatterns = () => request<DismissedPatternOut[]>("/api/incidents/dismissed-patterns");
export const removeDismissedPattern = (id: number) =>
  request<{ ok: boolean }>(`/api/incidents/dismissed-patterns/${id}`, { method: "DELETE" });

// -------------------------------------------------------------- findings --
export const listFindings = (status?: string) =>
  request<FindingOut[]>(`/api/findings${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const updateFindingStatus = (id: number, status: string, dismissedReason?: string) =>
  request<{ ok: boolean }>(`/api/findings/${id}/status`, {
    method: "PATCH", body: JSON.stringify({ status, dismissed_reason: dismissedReason }),
  });
export const createActionForFinding = (findingId: number, payload: {
  action_taken: string; owner: string; due_date: string; expected_savings: number | null; notes: string;
}) => request<ActionOut>(`/api/findings/${findingId}/actions`, {
  method: "POST", body: JSON.stringify({ finding_id: findingId, ...payload }),
});

// --------------------------------------------------------------- actions --
export const listActions = (findingId?: number) =>
  request<ActionOut[]>(`/api/actions${findingId ? `?finding_id=${findingId}` : ""}`);
export const updateAction = (id: number, payload: Partial<{
  status: string; notes: string; confirmed_savings: number; owner: string; due_date: string;
}>) => request<ActionOut>(`/api/actions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

// -------------------------------------------------------------- settings --
export const getSettings = () => request<ThresholdSettings>("/api/settings");
export const updateSettings = (payload: ThresholdSettings) =>
  request<ThresholdSettings>("/api/settings", { method: "PATCH", body: JSON.stringify(payload) });
export const previewOccupancyImport = async (file: File): Promise<OccupancyImportRow[]> => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/settings/occupancy/preview`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json();
};
export const commitOccupancyImport = async (file: File): Promise<{ imported: number; skipped: number }> => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/settings/occupancy/import`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json();
};
export const createBackup = () => request<{ ok: boolean; message: string }>("/api/settings/backup", { method: "POST" });
export const getExportUrl = () => `${API_BASE}/api/settings/export`;
export const getReportUrl = (fmt: "md" | "csv" | "pdf", month?: string) =>
  `${API_BASE}/api/settings/report?fmt=${fmt}${month ? `&month=${month}` : ""}`;

export { ApiError };
