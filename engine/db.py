"""
db.py — SQLite schema and helpers for the Invoice Review app (Draft 2).

Two databases are kept separate on purpose (item 15, "Data Safety and Testing"):
set INVOICE_APP_ENV=production to point at the production file; anything else
(default "demo") uses a separate file, so testing/demoing can never touch real data.
"""

import os
import sqlite3
import shutil
import json
import csv
import io
import zipfile
from pathlib import Path
from datetime import datetime, timezone

APP_DIR = Path(__file__).parent
PROJECT_ROOT = APP_DIR.parent  # invoice_app/ — engine/ lives one level below it
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ENV = os.environ.get("INVOICE_APP_ENV", "demo")
if ENV not in ("demo", "production"):
    ENV = "demo"
DB_PATH = DATA_DIR / f"invoice_review_{ENV}.db"

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT,
    units INTEGER,
    sqft INTEGER,
    construction_year INTEGER,
    heating_type TEXT,
    metering_type TEXT
);

CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filehash TEXT NOT NULL UNIQUE,
    filetype TEXT,
    stored_path TEXT,
    uploaded_at TEXT,
    status TEXT DEFAULT 'pending_review',
    duplicate_status TEXT DEFAULT 'unique',
    duplicate_of_id INTEGER REFERENCES source_files(id),
    raw_text TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_id INTEGER REFERENCES source_files(id),
    property_id INTEGER REFERENCES properties(id),
    category TEXT,
    vendor TEXT,
    invoice_number TEXT,
    billing_start TEXT,
    billing_end TEXT,
    consumption REAL,
    consumption_unit TEXT,
    taxes_fees REAL,
    total_cost REAL,
    approved INTEGER DEFAULT 0,
    notes TEXT,
    field_confidence TEXT,
    validation_errors TEXT,
    logical_duplicate_of INTEGER REFERENCES invoices(id),
    duplicate_override INTEGER DEFAULT 0,
    approved_by TEXT,
    last_modified_by TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS occupancy_months (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER REFERENCES properties(id),
    month TEXT,
    occupied_units INTEGER,
    vacant_units INTEGER,
    UNIQUE(property_id, month)
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER REFERENCES properties(id),
    category TEXT,
    description TEXT,
    evidence TEXT,
    observed_excess REAL,
    recommended_action TEXT,
    severity TEXT,
    confidence TEXT,
    cause TEXT,
    owner TEXT,
    status TEXT DEFAULT 'New',
    source_invoice_ids TEXT,
    dismissed_reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER REFERENCES findings(id),
    action_taken TEXT,
    owner TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'New',          -- New | Investigating | Actioned | Resolved
    notes TEXT,
    expected_savings REAL,
    confirmed_savings REAL,
    date TEXT,
    result TEXT
);

CREATE TABLE IF NOT EXISTS dismissed_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER REFERENCES properties(id),
    category TEXT,
    rule TEXT,
    reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER REFERENCES invoices(id),
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT,
    changed_at TEXT
);
"""

DEFAULT_SETTINGS = {
    "threshold_yoy_pct": "15",
    "threshold_usage_pct": "20",
    "threshold_rate_pct": "10",
    "threshold_sustained_months": "2",
    "threshold_stddev": "2",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    run_migrations(conn)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


def run_migrations(conn):
    """Minimal version-gated migration path. Safe to call repeatedly."""
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    current = int(row["value"]) if row else 0

    if current < 1:
        conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '1')")
        current = 1

    if current < 2:
        # v2 schema was authored fresh (CREATE TABLE IF NOT EXISTS already covers it).
        # Placeholder kept so future schema changes have a clear ALTER TABLE pattern.
        conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '2')")
        current = 2

    if current < 3:
        # v3: actions table gained owner/due_date/status/notes/savings columns,
        # dismissed_patterns and audit_log added. CREATE TABLE IF NOT EXISTS
        # handles fresh installs; ALTER TABLE covers upgrading an existing v2 db.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(actions)").fetchall()}
        for col, coltype in [
            ("owner", "TEXT"), ("due_date", "TEXT"), ("status", "TEXT DEFAULT 'New'"),
            ("notes", "TEXT"), ("expected_savings", "REAL"), ("confirmed_savings", "REAL"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE actions ADD COLUMN {col} {coltype}")
        conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '3')")
        current = 3

    if current < 4:
        # v4: accountability — record who approved/last touched each invoice.
        existing_inv_cols = {row["name"] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()}
        for col, coltype in [("approved_by", "TEXT"), ("last_modified_by", "TEXT")]:
            if col not in existing_inv_cols:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} {coltype}")
        conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', '4')")
        current = 4

    conn.commit()


# ---------------------------------------------------------------- settings --

def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def get_all_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_thresholds(conn):
    """Single source of truth for anomaly thresholds, used by both analysis.py
    (baseline/cause classification) and anomalies.py (rule engine)."""
    s = get_all_settings(conn)
    return {
        "yoy_pct": float(s.get("threshold_yoy_pct", 15)),
        "usage_pct": float(s.get("threshold_usage_pct", 20)),
        "rate_pct": float(s.get("threshold_rate_pct", 10)),
        "sustained_months": int(s.get("threshold_sustained_months", 2)),
        "stddev": float(s.get("threshold_stddev", 2)),
    }


# --------------------------------------------------------------- properties --

def list_properties(conn):
    return conn.execute("SELECT * FROM properties ORDER BY name").fetchall()


def get_property(conn, property_id):
    return conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()


def add_property(conn, name, address="", units=None, sqft=None,
                  construction_year=None, heating_type="", metering_type=""):
    conn.execute(
        """INSERT OR IGNORE INTO properties
           (name, address, units, sqft, construction_year, heating_type, metering_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, address, units, sqft, construction_year, heating_type, metering_type),
    )
    conn.commit()


# -------------------------------------------------------------- source_files --

def get_source_file_by_hash(conn, filehash):
    return conn.execute("SELECT * FROM source_files WHERE filehash = ?", (filehash,)).fetchone()


def insert_source_file(conn, filename, filehash, filetype, stored_path, raw_text,
                        duplicate_status="unique", duplicate_of_id=None):
    cur = conn.execute(
        """INSERT INTO source_files
           (filename, filehash, filetype, stored_path, uploaded_at, status,
            duplicate_status, duplicate_of_id, raw_text)
           VALUES (?, ?, ?, ?, ?, 'pending_review', ?, ?, ?)""",
        (filename, filehash, filetype, stored_path, now_iso(),
         duplicate_status, duplicate_of_id, raw_text),
    )
    conn.commit()
    return cur.lastrowid


def list_source_files(conn, status=None):
    if status:
        return conn.execute(
            "SELECT * FROM source_files WHERE status = ? ORDER BY uploaded_at DESC", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM source_files ORDER BY uploaded_at DESC").fetchall()


def set_source_file_status(conn, source_file_id, status):
    conn.execute("UPDATE source_files SET status = ? WHERE id = ?", (status, source_file_id))
    conn.commit()


# ----------------------------------------------------------------- invoices --

def insert_draft_invoice(conn, source_file_id, fields, field_confidence=None):
    cur = conn.execute(
        """INSERT INTO invoices
           (source_file_id, property_id, category, vendor, invoice_number,
            billing_start, billing_end, consumption, consumption_unit,
            taxes_fees, total_cost, approved, notes, field_confidence,
            validation_errors, logical_duplicate_of, duplicate_override, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0, ?)""",
        (
            source_file_id,
            fields.get("property_id"),
            fields.get("category", ""),
            fields.get("vendor", ""),
            fields.get("invoice_number", ""),
            fields.get("billing_start", ""),
            fields.get("billing_end", ""),
            fields.get("consumption"),
            fields.get("consumption_unit", ""),
            fields.get("taxes_fees"),
            fields.get("total_cost"),
            fields.get("notes", ""),
            json.dumps(field_confidence or {}),
            "",
            None,
            now_iso(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_invoice(conn, invoice_id):
    return conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()


def get_invoice_for_source_file(conn, source_file_id):
    return conn.execute(
        "SELECT * FROM invoices WHERE source_file_id = ?", (source_file_id,)
    ).fetchone()


def update_invoice(conn, invoice_id, fields, validation_errors=None,
                    logical_duplicate_of=None, duplicate_override=None,
                    changed_by=""):
    existing = get_invoice(conn, invoice_id)
    tracked_fields = [
        "property_id", "category", "vendor", "invoice_number",
        "billing_start", "billing_end", "consumption", "consumption_unit",
        "taxes_fees", "total_cost", "notes",
    ]
    for f in tracked_fields:
        old_value = existing[f]
        new_value = fields.get(f)
        log_invoice_change(conn, invoice_id, f, old_value, new_value, changed_by)

    conn.execute(
        """UPDATE invoices SET
           property_id=?, category=?, vendor=?, invoice_number=?,
           billing_start=?, billing_end=?, consumption=?, consumption_unit=?,
           taxes_fees=?, total_cost=?, notes=?, validation_errors=?,
           logical_duplicate_of=?, duplicate_override=?, last_modified_by=?
           WHERE id=?""",
        (
            fields.get("property_id"),
            fields.get("category", ""),
            fields.get("vendor", ""),
            fields.get("invoice_number", ""),
            fields.get("billing_start", ""),
            fields.get("billing_end", ""),
            fields.get("consumption"),
            fields.get("consumption_unit", ""),
            fields.get("taxes_fees"),
            fields.get("total_cost"),
            fields.get("notes", ""),
            "|".join(validation_errors or []),
            logical_duplicate_of if logical_duplicate_of is not None else existing["logical_duplicate_of"],
            int(duplicate_override) if duplicate_override is not None else existing["duplicate_override"],
            changed_by or existing["last_modified_by"],
            invoice_id,
        ),
    )
    conn.commit()


def approve_invoice(conn, invoice_id, source_file_id, approved_by=""):
    conn.execute(
        "UPDATE invoices SET approved = 1, approved_by = ?, last_modified_by = ? WHERE id = ?",
        (approved_by, approved_by, invoice_id),
    )
    conn.execute("UPDATE source_files SET status = 'approved' WHERE id = ?", (source_file_id,))
    log_invoice_change(conn, invoice_id, "approved", 0, 1, approved_by)
    conn.commit()


def reject_invoice(conn, invoice_id, source_file_id):
    conn.execute("UPDATE invoices SET approved = 0 WHERE id = ?", (invoice_id,))
    conn.execute("UPDATE source_files SET status = 'rejected' WHERE id = ?", (source_file_id,))
    conn.commit()


def list_invoices_with_files(conn):
    return conn.execute(
        """SELECT invoices.*, source_files.filename, source_files.filetype,
                  source_files.status AS file_status,
                  source_files.duplicate_status, properties.name AS property_name
           FROM invoices
           JOIN source_files ON invoices.source_file_id = source_files.id
           LEFT JOIN properties ON invoices.property_id = properties.id
           ORDER BY invoices.created_at DESC"""
    ).fetchall()


def list_approved_invoices(conn, property_id=None, category=None):
    query = """SELECT invoices.*, properties.name AS property_name
               FROM invoices
               LEFT JOIN properties ON invoices.property_id = properties.id
               WHERE approved = 1"""
    params = []
    if property_id:
        query += " AND invoices.property_id = ?"
        params.append(property_id)
    if category:
        query += " AND invoices.category = ?"
        params.append(category)
    query += " ORDER BY billing_start"
    return conn.execute(query, params).fetchall()


def list_invoices_for_duplicate_check(conn, property_id, category, exclude_id=None):
    query = "SELECT * FROM invoices WHERE property_id = ? AND category = ?"
    params = [property_id, category]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchall()


# --------------------------------------------------------------- occupancy --

def upsert_occupancy(conn, property_id, month, occupied_units, vacant_units):
    conn.execute(
        """INSERT INTO occupancy_months (property_id, month, occupied_units, vacant_units)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(property_id, month) DO UPDATE SET
             occupied_units=excluded.occupied_units,
             vacant_units=excluded.vacant_units""",
        (property_id, month, occupied_units, vacant_units),
    )
    conn.commit()


def list_occupancy(conn, property_id=None):
    query = """SELECT occupancy_months.*, properties.name AS property_name
               FROM occupancy_months
               LEFT JOIN properties ON occupancy_months.property_id = properties.id"""
    params = []
    if property_id:
        query += " WHERE occupancy_months.property_id = ?"
        params.append(property_id)
    query += " ORDER BY month"
    return conn.execute(query, params).fetchall()


def get_occupancy(conn, property_id, month):
    return conn.execute(
        "SELECT * FROM occupancy_months WHERE property_id = ? AND month = ?",
        (property_id, month),
    ).fetchone()


# ----------------------------------------------------------------- findings --

def insert_finding(conn, property_id, category, description, evidence,
                    observed_excess, recommended_action, severity="Medium",
                    confidence="Possible", cause="Unknown", owner="",
                    source_invoice_ids=None):
    cur = conn.execute(
        """INSERT INTO findings
           (property_id, category, description, evidence, observed_excess,
            recommended_action, severity, confidence, cause, owner, status,
            source_invoice_ids, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?)""",
        (property_id, category, description, evidence, observed_excess,
         recommended_action, severity, confidence, cause, owner,
         ",".join(str(i) for i in (source_invoice_ids or [])), now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def list_findings(conn, status=None):
    query = """SELECT findings.*, properties.name AS property_name
               FROM findings LEFT JOIN properties ON findings.property_id = properties.id"""
    params = []
    if status:
        query += " WHERE findings.status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    return conn.execute(query, params).fetchall()


def update_finding_status(conn, finding_id, status, dismissed_reason=None):
    conn.execute(
        "UPDATE findings SET status = ?, dismissed_reason = COALESCE(?, dismissed_reason) WHERE id = ?",
        (status, dismissed_reason, finding_id),
    )
    conn.commit()


# -------------------------------------------------------------------- actions --

def insert_action(conn, finding_id, action_taken, owner="", due_date="",
                   status="New", notes="", expected_savings=None):
    cur = conn.execute(
        """INSERT INTO actions
           (finding_id, action_taken, owner, due_date, status, notes,
            expected_savings, confirmed_savings, date, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, '')""",
        (finding_id, action_taken, owner, due_date, status, notes, expected_savings, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def get_action(conn, action_id):
    return conn.execute(
        """SELECT actions.*, findings.description AS finding_description,
                  findings.property_id, properties.name AS property_name
           FROM actions
           LEFT JOIN findings ON actions.finding_id = findings.id
           LEFT JOIN properties ON findings.property_id = properties.id
           WHERE actions.id = ?""",
        (action_id,),
    ).fetchone()


def list_actions(conn, finding_id=None):
    query = """SELECT actions.*, findings.description AS finding_description,
                      findings.property_id, properties.name AS property_name
               FROM actions
               LEFT JOIN findings ON actions.finding_id = findings.id
               LEFT JOIN properties ON findings.property_id = properties.id"""
    params = []
    if finding_id:
        query += " WHERE actions.finding_id = ?"
        params.append(finding_id)
    query += " ORDER BY actions.id DESC"
    return conn.execute(query, params).fetchall()


def update_action(conn, action_id, status=None, notes=None, confirmed_savings=None,
                   owner=None, due_date=None):
    existing = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if not existing:
        return
    conn.execute(
        """UPDATE actions SET status=?, notes=?, confirmed_savings=?, owner=?, due_date=?
           WHERE id=?""",
        (
            status if status is not None else existing["status"],
            notes if notes is not None else existing["notes"],
            confirmed_savings if confirmed_savings is not None else existing["confirmed_savings"],
            owner if owner is not None else existing["owner"],
            due_date if due_date is not None else existing["due_date"],
            action_id,
        ),
    )
    conn.commit()


# ------------------------------------------------------------ dismissed patterns --

def dismiss_pattern(conn, property_id, category, rule, reason=""):
    conn.execute(
        """INSERT INTO dismissed_patterns (property_id, category, rule, reason, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (property_id, category, rule, reason, now_iso()),
    )
    conn.commit()


def list_dismissed_patterns(conn):
    return conn.execute(
        """SELECT dismissed_patterns.*, properties.name AS property_name
           FROM dismissed_patterns LEFT JOIN properties ON dismissed_patterns.property_id = properties.id
           ORDER BY created_at DESC"""
    ).fetchall()


def remove_dismissed_pattern(conn, pattern_id):
    conn.execute("DELETE FROM dismissed_patterns WHERE id = ?", (pattern_id,))
    conn.commit()


def is_pattern_dismissed(conn, property_id, category, rule):
    row = conn.execute(
        """SELECT 1 FROM dismissed_patterns
           WHERE property_id = ? AND category = ? AND rule = ? LIMIT 1""",
        (property_id, category, rule),
    ).fetchone()
    return row is not None


# ------------------------------------------------------------------- audit log --

def _normalize_for_compare(value):
    """None and '' are treated as equivalent (both mean 'not set'), and
    numeric-looking values are compared as floats so 1000 and 1000.0 don't
    register as a change. Anything else compares as a stripped string."""
    if value is None or value == "":
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value).strip()


def log_invoice_change(conn, invoice_id, field, old_value, new_value, changed_by):
    if _normalize_for_compare(old_value) == _normalize_for_compare(new_value):
        return
    conn.execute(
        """INSERT INTO audit_log (invoice_id, field, old_value, new_value, changed_by, changed_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (invoice_id, field, str(old_value), str(new_value), changed_by, now_iso()),
    )
    conn.commit()


def list_audit_log(conn, invoice_id=None):
    query = "SELECT * FROM audit_log"
    params = []
    if invoice_id:
        query += " WHERE invoice_id = ?"
        params.append(invoice_id)
    query += " ORDER BY changed_at DESC"
    return conn.execute(query, params).fetchall()


# ------------------------------------------------------------- data safety --

def backup_db(dest_path):
    dest = sqlite3.connect(dest_path)
    src = get_conn()
    src.backup(dest)
    dest.close()
    src.close()
    return dest_path


def restore_db(src_path):
    shutil.copyfile(src_path, DB_PATH)


def export_all_csv_zip():
    conn = get_conn()
    tables = ["properties", "source_files", "invoices", "occupancy_months", "findings", "actions"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            out = io.StringIO()
            if rows:
                writer = csv.DictWriter(out, fieldnames=rows[0].keys())
                writer.writeheader()
                for r in rows:
                    writer.writerow(dict(r))
            zf.writestr(f"{table}.csv", out.getvalue())
    conn.close()
    buf.seek(0)
    return buf.read()
