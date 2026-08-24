"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSettings, updateSettings, previewOccupancyImport, commitOccupancyImport,
  createBackup, getExportUrl, getReportUrl, listDismissedPatterns, removeDismissedPattern,
  type ThresholdSettings,
} from "@/lib/api";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Upload, Download, Save, Trash2 } from "lucide-react";

const TABS = ["Anomaly thresholds", "Occupancy import", "Data safety", "Dismissed patterns"] as const;
type Tab = (typeof TABS)[number];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("Anomaly thresholds");

  return (
    <div className="mx-auto max-w-[1000px] p-6">
      <h1 className="text-page-title mb-4">Settings</h1>
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

      {tab === "Anomaly thresholds" && <ThresholdsTab />}
      {tab === "Occupancy import" && <OccupancyImportTab />}
      {tab === "Data safety" && <DataSafetyTab />}
      {tab === "Dismissed patterns" && <DismissedPatternsTab />}
    </div>
  );
}

function ThresholdsTab() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [form, setForm] = useState<ThresholdSettings | null>(null);
  const current = form || settings || null;

  const mutation = useMutation({
    mutationFn: (payload: ThresholdSettings) => updateSettings(payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setForm(data);
    },
  });

  if (isLoading || !current) {
    return <Surface className="p-6 text-[13px] text-[var(--color-ink-faint)]">Loading…</Surface>;
  }

  function update<K extends keyof ThresholdSettings>(key: K, value: ThresholdSettings[K]) {
    setForm({ ...current!, [key]: value });
  }

  return (
    <Surface>
      <SurfaceHeader title="Anomaly Rules V1 thresholds" />
      <div className="grid grid-cols-2 gap-4 p-5">
        <ThresholdField
          label="Year-over-year cost increase (%)"
          value={current.threshold_yoy_pct}
          onChange={(v) => update("threshold_yoy_pct", v)}
        />
        <ThresholdField
          label="Usage per occupied unit above baseline (%)"
          value={current.threshold_usage_pct}
          onChange={(v) => update("threshold_usage_pct", v)}
        />
        <ThresholdField
          label="Effective rate above baseline (%)"
          value={current.threshold_rate_pct}
          onChange={(v) => update("threshold_rate_pct", v)}
        />
        <ThresholdField
          label="Sustained condition (consecutive months)"
          value={current.threshold_sustained_months}
          onChange={(v) => update("threshold_sustained_months", v)}
        />
        <ThresholdField
          label="Standard deviations above history"
          value={current.threshold_stddev}
          onChange={(v) => update("threshold_stddev", v)}
        />
      </div>
      <div className="border-t border-[var(--color-hairline)] px-5 py-3">
        <Button variant="primary" size="sm" onClick={() => mutation.mutate(current)} disabled={mutation.isPending}>
          <Save size={14} /> Save thresholds
        </Button>
        {mutation.isSuccess && <span className="ml-2 text-[12.5px] text-[var(--color-good)]">Saved.</span>}
      </div>
    </Surface>
  );
}

function ThresholdField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="text-label mb-1">{label}</div>
      <Input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function OccupancyImportTab() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof previewOccupancyImport>> | null>(null);

  const previewMutation = useMutation({
    mutationFn: (f: File) => previewOccupancyImport(f),
    onSuccess: (rows) => setPreview(rows),
  });
  const commitMutation = useMutation({
    mutationFn: (f: File) => commitOccupancyImport(f),
  });

  return (
    <Surface>
      <SurfaceHeader title="Import occupancy from CSV/Excel" />
      <div className="p-5">
        <p className="mb-3 text-[13px] text-[var(--color-ink-muted)]">
          Expected columns: <code>property</code>, <code>month</code>, <code>occupied_units</code>, <code>vacant_units</code>.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              setFile(f);
              setPreview(null);
              previewMutation.mutate(f);
            }
          }}
        />
        <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>
          <Upload size={14} /> Choose file
        </Button>
        {file && <span className="ml-2 text-[13px] text-[var(--color-ink-muted)]">{file.name}</span>}

        {preview && (
          <div className="mt-4">
            <div className="text-label mb-2">Validation preview ({preview.length} rows)</div>
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                  <th className="py-1.5 pr-3">Property</th>
                  <th className="py-1.5 pr-3">Month</th>
                  <th className="py-1.5 pr-3">Occupied</th>
                  <th className="py-1.5 pr-3">Vacant</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row, i) => (
                  <tr key={i} className="border-b border-[var(--color-hairline)] last:border-0">
                    <td className="py-1.5 pr-3">{row.property_name}</td>
                    <td className="py-1.5 pr-3">{row.month}</td>
                    <td className="py-1.5 pr-3">{row.occupied_units}</td>
                    <td className="py-1.5 pr-3">{row.vacant_units}</td>
                    <td className="py-1.5">
                      {row.valid ? (
                        <span className="text-[var(--color-good)]">Valid</span>
                      ) : (
                        <span className="text-[var(--color-critical)]">{row.reason}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3">
              <Button
                variant="primary"
                size="sm"
                disabled={!file || commitMutation.isPending}
                onClick={() => file && commitMutation.mutate(file)}
              >
                Import valid rows
              </Button>
              {commitMutation.isSuccess && (
                <span className="ml-2 text-[12.5px] text-[var(--color-good)]">
                  Imported {commitMutation.data.imported}, skipped {commitMutation.data.skipped}.
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </Surface>
  );
}

function DataSafetyTab() {
  const backupMutation = useMutation({ mutationFn: createBackup });
  const [reportMonth, setReportMonth] = useState("");

  return (
    <div className="space-y-4">
      <Surface>
        <SurfaceHeader title="Backup & export" />
        <div className="flex flex-wrap gap-2 p-5">
          <Button variant="secondary" size="sm" onClick={() => backupMutation.mutate()} disabled={backupMutation.isPending}>
            Create backup now
          </Button>
          {backupMutation.isSuccess && (
            <span className="self-center text-[12.5px] text-[var(--color-good)]">{backupMutation.data.message}</span>
          )}
          <a href={getExportUrl()}>
            <Button variant="secondary" size="sm">
              <Download size={14} /> Export all data (CSV zip)
            </Button>
          </a>
        </div>
      </Surface>

      <Surface>
        <SurfaceHeader title="Monthly action report" />
        <div className="flex flex-wrap items-center gap-2 p-5">
          <Input
            placeholder="Month filter (YYYY-MM, optional)"
            value={reportMonth}
            onChange={(e) => setReportMonth(e.target.value)}
            className="w-56"
          />
          <a href={getReportUrl("md", reportMonth || undefined)}>
            <Button variant="secondary" size="sm"><Download size={14} /> Markdown</Button>
          </a>
          <a href={getReportUrl("csv", reportMonth || undefined)}>
            <Button variant="secondary" size="sm"><Download size={14} /> CSV</Button>
          </a>
          <a href={getReportUrl("pdf", reportMonth || undefined)}>
            <Button variant="secondary" size="sm"><Download size={14} /> PDF</Button>
          </a>
        </div>
      </Surface>
    </div>
  );
}

function DismissedPatternsTab() {
  const queryClient = useQueryClient();
  const { data: patterns, isLoading } = useQuery({ queryKey: ["dismissed-patterns"], queryFn: listDismissedPatterns });
  const removeMutation = useMutation({
    mutationFn: (id: number) => removeDismissedPattern(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dismissed-patterns"] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  return (
    <Surface>
      <SurfaceHeader title="Dismissed patterns" />
      {isLoading ? (
        <div className="p-8 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
      ) : !patterns || patterns.length === 0 ? (
        <div className="p-8 text-center text-[13px] text-[var(--color-ink-faint)]">Nothing dismissed yet.</div>
      ) : (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[var(--color-hairline)] text-left text-label">
              <th className="px-4 py-2 font-medium">Property</th>
              <th className="px-2 py-2 font-medium">Category</th>
              <th className="px-2 py-2 font-medium">Rule</th>
              <th className="px-2 py-2 font-medium">Reason</th>
              <th className="px-2 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {patterns.map((p) => (
              <tr key={p.id} className="border-b border-[var(--color-hairline)] last:border-0">
                <td className="px-4 py-2.5">{p.property_name}</td>
                <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{p.category}</td>
                <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{p.rule.replace(/_/g, " ")}</td>
                <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{p.reason || "—"}</td>
                <td className="px-2 py-2.5">
                  <button
                    onClick={() => removeMutation.mutate(p.id)}
                    className="text-[var(--color-ink-faint)] hover:text-[var(--color-critical)]"
                    title="Re-enable this rule for this property"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Surface>
  );
}
