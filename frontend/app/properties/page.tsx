"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus } from "lucide-react";
import { listProperties, createProperty } from "@/lib/api";
import { Surface, SurfaceHeader } from "@/components/ui/surface";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function PropertiesPage() {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [units, setUnits] = useState<number | "">("");
  const queryClient = useQueryClient();

  const { data: properties, isLoading } = useQuery({ queryKey: ["properties"], queryFn: listProperties });

  const createMutation = useMutation({
    mutationFn: () => createProperty({ name, address, units: units === "" ? null : Number(units) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["properties"] });
      setShowForm(false);
      setName("");
      setAddress("");
      setUnits("");
    },
  });

  return (
    <div className="mx-auto max-w-[1400px] p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-page-title">Properties</h1>
        <Button variant="primary" size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus size={14} /> Add property
        </Button>
      </div>

      {showForm && (
        <Surface className="mb-5 p-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-label mb-1">Name</div>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <div className="text-label mb-1">Address</div>
              <Input value={address} onChange={(e) => setAddress(e.target.value)} />
            </div>
            <div>
              <div className="text-label mb-1">Units</div>
              <Input type="number" value={units} onChange={(e) => setUnits(e.target.value ? Number(e.target.value) : "")} />
            </div>
          </div>
          <div className="mt-3">
            <Button variant="primary" size="sm" disabled={!name || createMutation.isPending} onClick={() => createMutation.mutate()}>
              Save property
            </Button>
          </div>
        </Surface>
      )}

      <Surface>
        {isLoading ? (
          <div className="p-10 text-center text-[13px] text-[var(--color-ink-faint)]">Loading…</div>
        ) : !properties || properties.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-10 text-center">
            <Building2 size={20} className="text-[var(--color-ink-faint)]" />
            <div className="text-[13.5px] font-medium">No properties yet</div>
            <div className="text-[13px] text-[var(--color-ink-faint)]">Add your first property to start tracking invoices.</div>
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-hairline)] text-left text-label">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-2 py-2 font-medium">Address</th>
                <th className="px-2 py-2 font-medium text-right">Units</th>
                <th className="px-2 py-2 font-medium">Metering</th>
              </tr>
            </thead>
            <tbody>
              {properties.map((p) => (
                <tr key={p.id} className="border-b border-[var(--color-hairline)] last:border-0 hover:bg-[var(--color-surface-muted)]">
                  <td className="px-4 py-2.5">
                    <Link href={`/properties/${p.id}`} className="font-medium text-[var(--color-ink)] hover:text-[var(--color-brand)]">
                      {p.name}
                    </Link>
                  </td>
                  <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{p.address || "—"}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{p.units ?? "—"}</td>
                  <td className="px-2 py-2.5 text-[var(--color-ink-muted)]">{p.metering_type || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Surface>
    </div>
  );
}
