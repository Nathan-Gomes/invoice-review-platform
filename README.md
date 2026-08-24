# Invoice Review — FastAPI + Next.js

A Python engine (extraction, validation, analysis, anomaly detection, incident
triage, reporting), exposed through a FastAPI backend, with a Next.js/
TypeScript frontend. The original Streamlit app still works and lives in
`streamlit_legacy/` as a fallback — all three share the same database.

```
Next.js frontend  --HTTP/JSON-->  FastAPI backend  -->  engine/  -->  SQLite
                                                                  \-> invoice PDFs (data/uploads)
```

## Running it

**Terminal 1 — backend** (from `invoice_app/`):
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — frontend** (from `invoice_app/frontend/`):
```bash
npm install
npm run dev     # http://localhost:3000
```

**Optional — Streamlit fallback** (from `invoice_app/`, same venv):
```bash
streamlit run streamlit_legacy/app.py     # http://localhost:8501
```

All three read/write `data/invoice_review_demo.db` and `data/uploads/`, so
data created in one shows up in the others immediately.

## Pages — all built, no more placeholders

| Route | What it does |
|---|---|
| `/overview` | Metric strip, ranked Needs Attention table, portfolio trend + category charts, top properties by excess, recent actions |
| `/triage` | Compact incident table (filter/search/sort) + right-side detail panel with Dismiss / Confirm / Investigate / Create Action |
| `/properties` | Property list, add new property |
| `/properties/[id]` | Header (units, occupancy, spend, YoY, open incidents) + 5 sub-tabs: Summary (trend chart, click a point to open its invoice), Utilities, Invoices, Occupancy, Findings & Actions |
| `/invoices` | Queue: search, state filter, batch-approve for clean high-confidence invoices, upload |
| `/invoices/[id]` | Two-column review workspace: PDF viewer / grouped field form with inline confidence + validation + duplicate comparison, sticky approve bar, previous/next controls |
| `/analysis` | Ad hoc property/category/month lookup with trend chart, for digging into anything not on a property's curated page |
| `/findings` | Findings (status workflow, create actions inline) and Actions (owner/due date/expected-vs-confirmed savings) in two tabs |
| `/settings` | Anomaly thresholds, occupancy import (preview + validation before commit), backup/export/report generation, dismissed-patterns management |

## What "built" means here

Every page above was verified two ways, the same discipline used throughout
this project:
1. **`npm run build` passes** — real TypeScript errors were caught and fixed
   along the way (a Recharts v3 click-handler type change, a couple of
   `number | null` mismatches), not just written and assumed correct.
2. **Every endpoint each page depends on was hit directly** (via `curl`)
   with the *exact* payload shape the corresponding component constructs,
   confirming the JSON response matches the TypeScript interface field-for-
   field. This covers: overview aggregation, invoice upload/update/approve/
   audit, incident confirm/dismiss/create-action, finding status updates,
   action creation/updates, property detail/trend/occupancy, and settings
   (thresholds, occupancy import preview+commit, backup, report generation
   in md/csv/pdf).

**What this doesn't cover:** real browser/DOM rendering. Playwright and
Puppeteer both fetch their Chromium binaries from CDNs outside this
environment's network allowlist, so no headless-browser pass was possible.
The build type-checks and every API contract is verified against live data,
but nobody has watched these pages actually render and clicked through them
in a real browser. That's the one gap left for a human to close.

## Project layout

```
invoice_app/
├── engine/              # Pure Python — no Streamlit, no FastAPI
├── backend/             # FastAPI: main.py, routers/, schemas/, services/
├── frontend/             # Next.js — one folder per route under app/
│   ├── components/ui/    # Button, Input, StatusPill, Surface, MetricCard, StickyActionBar
│   ├── components/layout/# Sidebar
│   └── lib/               # api.ts (typed client), utils.ts, query-provider.tsx
├── streamlit_legacy/app.py
├── data/                 # Shared SQLite db + uploaded PDFs (created on first run)
└── tests/                # 37 engine tests
```

## Not built / deliberately deferred

- **Vendor-specific extraction patterns** — the parser is still one generic
  regex set.
- **Weather sensitivity** in baselines (heating/cooling degree days).
- **Report review-before-finalization** — reports generate and download
  immediately, no draft/approve step.
- **Auth + PostgreSQL** — deliberately not started, matching the plan's own
  stated trigger conditions (multiple simultaneous users, hosted deployment,
  larger portfolios) — none of which apply yet.
- **shadcn/ui's CLI** couldn't run (`ui.shadcn.com` is outside this
  environment's network allowlist); the underlying Radix UI primitives were
  installed directly via npm instead. Functionally equivalent, just not
  literally shadcn's generated component files.
