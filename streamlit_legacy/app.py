"""
Invoice Review app — Draft 3.

Seven screens: Overview, Triage, Property, Invoices, Analysis, Findings & Actions, Settings.
Run with:  streamlit run app.py
Set INVOICE_APP_ENV=production to use the production database (default: demo).
"""

import base64
import json
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # so `engine` package is importable

from engine import db
from engine import extraction
from engine import validation
from engine import analysis
from engine import anomalies
from engine import incidents
from engine import reporting

st.set_page_config(page_title="Invoice Review", layout="wide")

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"  # shared with FastAPI backend
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

db.init_db()
conn = db.get_conn()

CATEGORIES = ["Water", "Electricity", "Natural Gas", "Other"]
FINDING_STATUSES = ["New", "Reviewing", "Pending", "Recovered", "Closed", "Dismissed"]
ACTION_STATUSES = ["New", "Investigating", "Actioned", "Resolved"]
TIER_ICON = {"Critical": "\U0001f534", "Watch": "\U0001f7e0", "Informational": "\u26aa"}
CONFIDENCE_ICON = {"Strong": "\u25cf\u25cf\u25cf", "Likely": "\u25cf\u25cf\u25cb", "Possible": "\u25cf\u25cb\u25cb"}


# ---------------------------------------------------------------- helpers --

def operator_name():
    return st.session_state.get("operator_name", "").strip() or "unknown"


def setup_progress():
    properties = db.list_properties(conn)
    has_property = len(properties) > 0
    has_units = any(p["units"] for p in properties)
    has_occupancy = len(db.list_occupancy(conn)) > 0
    has_uploads = len(db.list_source_files(conn)) > 0
    has_reviewed = any(
        db.get_invoice_for_source_file(conn, f["id"]) and
        db.get_invoice_for_source_file(conn, f["id"])["approved"]
        for f in db.list_source_files(conn) if f["filetype"] == "pdf"
    )
    has_approved_data = len(db.list_approved_invoices(conn)) > 0

    return [
        ("Add a property", has_property),
        ("Enter units and property details", has_units),
        ("Import occupancy", has_occupancy),
        ("Upload invoices", has_uploads),
        ("Review extracted invoices", has_reviewed),
        ("Open monthly analysis", has_approved_data),
    ]


def analysis_is_unlocked():
    properties = db.list_properties(conn)
    return any(p["units"] for p in properties) and len(db.list_approved_invoices(conn)) > 0


def pdf_preview_html(file_bytes: bytes, height=500):
    b64 = base64.b64encode(file_bytes).decode()
    return f'<embed src="data:application/pdf;base64,{b64}" width="100%" height="{height}" type="application/pdf">'


def render_invoice_by_id(invoice_id):
    """Shared 'open this invoice' view used by Property page invoice history
    and chart-click, so both land on the same PDF + fields display."""
    inv = db.get_invoice(conn, invoice_id)
    if not inv:
        st.warning("Invoice not found.")
        return
    sf = next((f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"]), None)
    st.markdown(f"**Invoice #{inv['id']}** — {inv['vendor']} — {inv['billing_start']} to {inv['billing_end']}")
    c1, c2 = st.columns([1, 1])
    with c1:
        if sf and sf["filetype"] == "pdf" and Path(sf["stored_path"]).exists():
            file_bytes = Path(sf["stored_path"]).read_bytes()
            import streamlit.components.v1 as components
            components.html(pdf_preview_html(file_bytes, height=400), height=420, scrolling=True)
        elif sf:
            st.text_area("Raw text", sf["raw_text"] or "(no text)", height=300)
    with c2:
        st.write(f"**Total cost:** ${inv['total_cost']:,.2f}")
        st.write(f"**Consumption:** {inv['consumption']} {inv['consumption_unit']}")
        st.write(f"**Category:** {inv['category']}")
        st.write(f"**Approved by:** {inv['approved_by'] or '—'}")
        st.write(f"**Last modified by:** {inv['last_modified_by'] or '—'}")
        log = db.list_audit_log(conn, invoice_id=invoice_id)
        if log:
            with st.expander(f"Change history ({len(log)})"):
                for entry in log:
                    st.caption(
                        f"{entry['changed_at']} — {entry['changed_by'] or 'unknown'} changed "
                        f"**{entry['field']}**: `{entry['old_value']}` \u2192 `{entry['new_value']}`"
                    )


def incident_tier_groups(triaged):
    groups = {"Critical": [], "Watch": [], "Informational": []}
    for inc in triaged:
        groups.setdefault(inc["tier"], []).append(inc)
    return groups


def render_incident_card(inc, key_prefix):
    icon = TIER_ICON.get(inc["tier"], "\u26aa")
    conf_dots = CONFIDENCE_ICON.get(inc["confidence"], "")
    title = (
        f"{icon} **{inc['property_name']}** — {inc['category']} "
        f"({', '.join(r.replace('_', ' ') for r in inc['rules'])})"
    )
    with st.expander(f"{title} — ${inc['annualized_impact']:,.0f}/yr est."):
        st.write(f"**Tier:** {inc['tier']}  |  **Severity:** {inc['severity']}  |  "
                 f"**Confidence:** {inc['confidence']} {conf_dots}  |  **Cause:** {inc['cause']}")
        st.write(f"**Months involved:** {', '.join(inc['months'])}")
        for m in inc["messages"]:
            st.write(f"- {m}")

        latest_metrics = None
        for a in inc["anomalies"]:
            if a["month"] == inc["latest_month"] and a.get("metrics"):
                latest_metrics = a["metrics"]
                break
        if latest_metrics and latest_metrics.get("explanation"):
            st.info(latest_metrics["explanation"])

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("Dismiss", key=f"{key_prefix}_dismiss"):
            st.session_state[f"{key_prefix}_show_dismiss_reason"] = True
        if b2.button("Confirm", key=f"{key_prefix}_confirm"):
            fid = incidents.create_finding_from_incident(conn, inc)
            db.update_finding_status(conn, fid, "Reviewing")
            st.success("Confirmed — added to Findings as Reviewing.")
            st.session_state.pop("triaged_incidents", None)
            st.rerun()
        if b3.button("Investigate", key=f"{key_prefix}_investigate"):
            fid = incidents.create_finding_from_incident(
                conn, inc, recommended_action="Under investigation — cause not yet confirmed."
            )
            db.update_finding_status(conn, fid, "Reviewing")
            st.success("Marked for investigation — see Findings & Actions.")
            st.session_state.pop("triaged_incidents", None)
            st.rerun()
        if b4.button("Create action", key=f"{key_prefix}_create_action"):
            st.session_state[f"{key_prefix}_show_action_form"] = True

        if st.session_state.get(f"{key_prefix}_show_dismiss_reason"):
            reason = st.text_input("Reason for dismissing (remembered for this property/category)",
                                    key=f"{key_prefix}_reason")
            if st.button("Confirm dismissal", key=f"{key_prefix}_confirm_dismiss"):
                incidents.dismiss_incident(conn, inc, reason=reason)
                st.success("Dismissed — this signal combination won't resurface for this property/category.")
                st.session_state.pop("triaged_incidents", None)
                st.session_state.pop(f"{key_prefix}_show_dismiss_reason", None)
                st.rerun()

        if st.session_state.get(f"{key_prefix}_show_action_form"):
            with st.form(key=f"{key_prefix}_action_form"):
                owner = st.text_input("Owner")
                due_date = st.text_input("Due date (YYYY-MM-DD)")
                expected_savings = st.number_input("Expected annual savings ($)", min_value=0.0, step=50.0,
                                                     value=float(inc["annualized_impact"] or 0))
                notes = st.text_area("Notes")
                if st.form_submit_button("Create finding + action"):
                    fid = incidents.create_finding_from_incident(conn, inc)
                    db.update_finding_status(conn, fid, "Pending")
                    db.insert_action(conn, fid, f"Follow up on {inc['category']} at {inc['property_name']}",
                                      owner=owner, due_date=due_date, expected_savings=expected_savings,
                                      notes=notes)
                    st.success("Action created — see Findings & Actions.")
                    st.session_state.pop("triaged_incidents", None)
                    st.session_state.pop(f"{key_prefix}_show_action_form", None)
                    st.rerun()


# ------------------------------------------------------------------ nav ----

st.sidebar.title("Invoice Review")
st.sidebar.caption(f"Environment: **{db.ENV}**")
st.session_state.setdefault("operator_name", "")
st.session_state["operator_name"] = st.sidebar.text_input(
    "Your name (for approvals/changes)", st.session_state["operator_name"]
)

screen = st.sidebar.radio(
    "Screen", ["Overview", "Triage", "Property", "Invoices", "Analysis", "Findings & Actions", "Settings"]
)

progress = setup_progress()
done_count = sum(1 for _, d in progress if d)
st.sidebar.progress(done_count / len(progress))
with st.sidebar.expander(f"Guided setup ({done_count}/{len(progress)})", expanded=done_count < len(progress)):
    for label, is_done in progress:
        st.write(("\u2705 " if is_done else "\u2b1c ") + label)

if not analysis_is_unlocked() and screen in ("Triage", "Property", "Analysis", "Findings & Actions"):
    st.warning(
        "This screen needs at least one property with units and one approved invoice first. "
        "Complete the guided setup steps in the sidebar."
    )
    st.stop()


# ================================================================ OVERVIEW =
if screen == "Overview":
    st.header("Overview")

    files = db.list_source_files(conn)
    needs_review = [f for f in files if f["filetype"] == "pdf" and f["status"] == "pending_review"]

    triaged = incidents.get_triaged_incidents(conn) if analysis_is_unlocked() else []
    groups = incident_tier_groups(triaged)
    total_excess = sum((inc["annualized_impact"] or 0) for inc in triaged)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invoices needing review", len(needs_review))
    c2.metric("Critical incidents", len(groups["Critical"]))
    c3.metric("Watch incidents", len(groups["Watch"]))
    c4.metric("Estimated annual excess", f"${total_excess:,.0f}")

    st.subheader("Needs attention (top 5)")
    top5 = triaged[:5]
    if top5:
        for i, inc in enumerate(top5):
            render_incident_card(inc, key_prefix=f"overview_{i}")
    else:
        st.caption("Nothing flagged right now — run a scan from the Triage screen once data is in place.")

    st.subheader("Portfolio totals")
    properties = db.list_properties(conn)
    rows = []
    for p in properties:
        for cat in CATEGORIES:
            months = analysis.list_months_with_data(conn, p["id"], cat)
            if not months:
                continue
            latest = months[-1]
            metrics = analysis.compute_property_month_metrics(conn, p["id"], cat, latest)
            if metrics:
                rows.append({
                    "Property": p["name"], "Category": cat, "Month": latest,
                    "Total cost": metrics["total_cost"],
                    "YoY variance": metrics["yoy_variance_pct"],
                    "Observed excess": metrics["observed_excess"],
                })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch")
        by_property = df.groupby("Property")["Observed excess"].sum().sort_values(ascending=False)
        by_category = df.groupby("Category")["Observed excess"].sum().sort_values(ascending=False)
        pc1, pc2 = st.columns(2)
        with pc1:
            st.caption("Top properties by observed excess")
            st.bar_chart(by_property)
        with pc2:
            st.caption("Top categories by observed excess")
            st.bar_chart(by_category)
    else:
        st.caption("No approved invoices yet.")


# ================================================================== TRIAGE =
elif screen == "Triage":
    st.header("Anomaly Triage")
    st.write("Related signals are grouped into one incident per property/category, "
              "ranked by financial impact, severity, and confidence.")

    if st.button("Run triage scan") or "triaged_incidents" not in st.session_state:
        st.session_state["triaged_incidents"] = incidents.get_triaged_incidents(conn)

    triaged = st.session_state.get("triaged_incidents", [])
    groups = incident_tier_groups(triaged)

    tab_critical, tab_watch, tab_info = st.tabs([
        f"\U0001f534 Critical ({len(groups['Critical'])})",
        f"\U0001f7e0 Watch ({len(groups['Watch'])})",
        f"\u26aa Informational ({len(groups['Informational'])})",
    ])

    with tab_critical:
        if groups["Critical"]:
            for i, inc in enumerate(groups["Critical"]):
                render_incident_card(inc, key_prefix=f"crit_{i}")
        else:
            st.caption("No critical incidents.")

    with tab_watch:
        if groups["Watch"]:
            for i, inc in enumerate(groups["Watch"]):
                render_incident_card(inc, key_prefix=f"watch_{i}")
        else:
            st.caption("No watch-tier incidents.")

    with tab_info:
        if groups["Informational"]:
            for i, inc in enumerate(groups["Informational"]):
                render_incident_card(inc, key_prefix=f"info_{i}")
        else:
            st.caption("No informational items.")

    with st.expander("Dismissed patterns"):
        patterns = db.list_dismissed_patterns(conn)
        if patterns:
            df = pd.DataFrame([dict(p) for p in patterns])[
                ["property_name", "category", "rule", "reason", "created_at"]
            ]
            st.dataframe(df, width="stretch")
            remove_id = st.number_input("Pattern ID to remove (re-enable)", min_value=0, step=1)
            if st.button("Remove dismissal") and remove_id:
                db.remove_dismissed_pattern(conn, int(remove_id))
                st.session_state.pop("triaged_incidents", None)
                st.success("Removed — this pattern can fire again on the next scan.")
                st.rerun()
        else:
            st.caption("Nothing dismissed yet.")


# ================================================================ PROPERTY =
elif screen == "Property":
    st.header("Property Investigation")

    properties = db.list_properties(conn)
    prop_names = [p["name"] for p in properties]
    prop_choice = st.selectbox("Property", prop_names)
    prop = next(p for p in properties if p["name"] == prop_choice)
    pid = prop["id"]

    st.subheader("Current-month spending")
    current_rows = []
    for cat in CATEGORIES:
        months = analysis.list_months_with_data(conn, pid, cat)
        if months:
            metrics = analysis.compute_property_month_metrics(conn, pid, cat, months[-1])
            if metrics:
                current_rows.append({
                    "Category": cat, "Month": months[-1], "Total cost": metrics["total_cost"],
                    "Expected cost": metrics["expected_cost"], "Observed excess": metrics["observed_excess"],
                    "YoY variance": metrics["yoy_variance_pct"], "Cause": metrics["cause"],
                    "Baseline confidence": metrics["baseline_confidence"],
                })
    if current_rows:
        st.dataframe(pd.DataFrame(current_rows), width="stretch")
    else:
        st.caption("No approved invoices yet for this property.")

    st.subheader("12-month trend (click a point to open its invoice)")
    category_for_trend = st.selectbox("Category for trend chart", CATEGORIES, key="trend_category")
    months = analysis.list_months_with_data(conn, pid, category_for_trend)
    trend_rows = []
    for m in months[-12:]:
        metrics = analysis.compute_property_month_metrics(conn, pid, category_for_trend, m)
        if metrics:
            trend_rows.append(metrics)

    if trend_rows:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[r["month"] for r in trend_rows], y=[r["total_cost"] for r in trend_rows],
            mode="lines+markers", name="Total cost",
            customdata=[r["invoice_id"] for r in trend_rows],
        ))
        fig.add_trace(go.Scatter(
            x=[r["month"] for r in trend_rows],
            y=[r["expected_cost"] if r["expected_cost"] is not None else None for r in trend_rows],
            mode="lines", name="Expected (baseline)", line=dict(dash="dash"),
        ))
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
        selection = st.plotly_chart(fig, on_select="rerun", key="property_trend_chart")

        clicked_invoice_id = None
        if selection and selection.get("selection", {}).get("points"):
            point = selection["selection"]["points"][0]
            if "customdata" in point:
                cd = point["customdata"]
                clicked_invoice_id = cd[0] if isinstance(cd, list) else cd
        if clicked_invoice_id:
            st.divider()
            st.write("**Selected invoice:**")
            render_invoice_by_id(clicked_invoice_id)
    else:
        st.caption(f"No approved {category_for_trend} invoices yet.")

    st.subheader("Category breakdown (latest month per category)")
    if current_rows:
        breakdown = pd.DataFrame(current_rows).set_index("Category")["Total cost"]
        st.bar_chart(breakdown)

    st.subheader("Open anomalies for this property")
    all_incidents = incidents.get_triaged_incidents(conn)
    property_incidents = [inc for inc in all_incidents if inc["property_id"] == pid]
    if property_incidents:
        for i, inc in enumerate(property_incidents):
            render_incident_card(inc, key_prefix=f"prop_{pid}_{i}")
    else:
        st.caption("No open anomalies for this property.")

    st.subheader("Invoice history")
    history = db.list_approved_invoices(conn, property_id=pid)
    if history:
        df_hist = pd.DataFrame([dict(h) for h in history])[
            ["id", "category", "vendor", "billing_start", "billing_end", "total_cost"]
        ]
        event = st.dataframe(
            df_hist, width="stretch", on_select="rerun", selection_mode="single-row", key="invoice_history_table"
        )
        if event and event.get("selection", {}).get("rows"):
            row_idx = event["selection"]["rows"][0]
            selected_invoice_id = int(df_hist.iloc[row_idx]["id"])
            st.divider()
            render_invoice_by_id(selected_invoice_id)
    else:
        st.caption("No invoice history yet.")


# ================================================================ INVOICES =
elif screen == "Invoices":
    st.header("Invoices")
    tab_queue, tab_upload = st.tabs(["Queue", "Upload"])

    with tab_upload:
        st.write("Upload invoice PDFs, or Excel/CSV accounting exports.")
        uploaded_files = st.file_uploader(
            "Upload files", type=["pdf", "xlsx", "xls", "csv"], accept_multiple_files=True
        )
        if uploaded_files:
            for uf in uploaded_files:
                file_bytes = uf.read()
                fhash = extraction.file_fingerprint(file_bytes)
                existing = db.get_source_file_by_hash(conn, fhash)
                if existing:
                    st.warning(f"**{uf.name}** — identical file already uploaded as "
                               f"'{existing['filename']}' (skipped).")
                    continue

                stored_path = UPLOAD_DIR / f"{fhash[:12]}_{uf.name}"
                stored_path.write_bytes(file_bytes)

                if uf.name.lower().endswith(".pdf"):
                    text, has_text = extraction.extract_pdf_text(file_bytes)
                    sf_id = db.insert_source_file(conn, uf.name, fhash, "pdf", str(stored_path), text)
                    fields, confidence = extraction.parse_invoice_fields(text)
                    inv_id = db.insert_draft_invoice(conn, sf_id, fields, confidence)
                    initial_errors = validation.validate_invoice(fields)
                    db.update_invoice(conn, inv_id, fields, validation_errors=initial_errors,
                                       changed_by="extraction")
                    if has_text:
                        st.success(f"**{uf.name}** — uploaded, fields extracted. Review in the Queue tab.")
                    else:
                        st.error(f"**{uf.name}** — no extractable text (likely scanned). "
                                 f"Flagged for OCR/manual entry.")
                else:
                    try:
                        df_preview = extraction.read_tabular_file(file_bytes, uf.name)
                        preview_text = df_preview.head(20).to_csv(index=False)
                    except Exception as e:
                        df_preview, preview_text = None, f"Could not parse file: {e}"
                    sf_id = db.insert_source_file(conn, uf.name, fhash, "tabular", str(stored_path), preview_text)
                    db.set_source_file_status(conn, sf_id, "approved")
                    st.success(f"**{uf.name}** — stored as accounting export.")
                    if df_preview is not None:
                        st.dataframe(df_preview.head(20))

    with tab_queue:
        invoices = db.list_invoices_with_files(conn)
        pdf_invoices = [i for i in invoices if i["filetype"] == "pdf"]

        def row_state(inv):
            if inv["duplicate_status"] == "file_duplicate":
                return "Duplicate"
            if inv["logical_duplicate_of"] and not inv["duplicate_override"]:
                return "Duplicate"
            if inv["validation_errors"]:
                return "Problem"
            if inv["approved"]:
                return "Approved"
            return "Needs Review"

        def is_high_confidence_clean(inv):
            if row_state(inv) != "Needs Review":
                return False
            try:
                conf = json.loads(inv["field_confidence"] or "{}")
            except Exception:
                return False
            # Only the fields validation.py actually requires matter here —
            # "notes" is never scored by the extractor (always 0.0) and would
            # otherwise make every invoice fail this check.
            required = ["vendor", "billing_start", "billing_end", "consumption",
                        "consumption_unit", "total_cost"]
            scores = [conf.get(f, 0.0) for f in required]
            if not scores:
                return False
            return all(s >= 0.6 for s in scores)

        filter_choice = st.radio(
            "Filter", ["All", "Needs Review", "Approved", "Duplicate", "Problem"], horizontal=True,
        )

        rows = []
        for inv in pdf_invoices:
            state = row_state(inv)
            if filter_choice != "All" and state != filter_choice:
                continue
            rows.append({
                "id": inv["id"], "Filename": inv["filename"],
                "Property": inv["property_name"] or "(unassigned)", "Vendor": inv["vendor"],
                "Billing period": f"{inv['billing_start']} \u2192 {inv['billing_end']}",
                "Total": inv["total_cost"], "State": state,
                "High-confidence": is_high_confidence_clean(inv),
            })

        clean_ids = [r["id"] for r in rows if r["High-confidence"]]
        if clean_ids:
            st.info(f"{len(clean_ids)} invoice(s) in this view are high-confidence and have no "
                    f"validation problems or duplicate flags.")
            if st.button(f"Batch approve {len(clean_ids)} clean invoice(s)"):
                approved_count = 0
                for inv_id in clean_ids:
                    inv = db.get_invoice(conn, inv_id)
                    sf = next(f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"])
                    if inv["property_id"]:
                        db.approve_invoice(conn, inv_id, sf["id"], approved_by=operator_name())
                        approved_count += 1
                st.success(f"Batch approved {approved_count} invoice(s) "
                           f"({len(clean_ids) - approved_count} skipped — no property assigned).")
                st.rerun()

        if rows:
            display_df = pd.DataFrame(rows).drop(columns=["id"])
            st.dataframe(display_df, width="stretch")
            options = {f"[{r['id']}] {r['Filename']} \u2014 {r['State']}": r["id"] for r in rows}
            choice = st.selectbox("Open an invoice to review", list(options.keys()))
            selected_id = options[choice]
        else:
            st.caption("No invoices match this filter.")
            selected_id = None

        if selected_id:
            inv = db.get_invoice(conn, selected_id)
            sf = next(f for f in db.list_source_files(conn) if f["id"] == inv["source_file_id"])
            properties = db.list_properties(conn)

            st.divider()
            col1, col2 = st.columns([1, 1])

            with col1:
                st.subheader("Source document")
                if sf["filetype"] == "pdf" and Path(sf["stored_path"]).exists():
                    file_bytes = Path(sf["stored_path"]).read_bytes()
                    import streamlit.components.v1 as components
                    components.html(pdf_preview_html(file_bytes), height=520, scrolling=True)
                else:
                    st.text_area("Raw text", sf["raw_text"] or "(no text extracted)", height=450)

            with col2:
                confidence = {}
                try:
                    confidence = json.loads(inv["field_confidence"] or "{}")
                except Exception:
                    pass

                def label_with_confidence(field_key, label):
                    c = confidence.get(field_key, 0.0)
                    if c and c < 0.7:
                        return f"\u26a0\ufe0f {label} (low-confidence guess)"
                    return label

                st.subheader("Extracted fields \u2014 correct as needed")

                if sf["duplicate_status"] == "file_duplicate":
                    st.caption("Flagged as duplicate: identical file content already uploaded.")
                elif inv["logical_duplicate_of"]:
                    st.caption(
                        f"Flagged as duplicate of invoice #{inv['logical_duplicate_of']}: "
                        f"same vendor + invoice number, or same vendor + amount with an "
                        f"overlapping billing period."
                    )
                if inv["validation_errors"]:
                    st.caption(f"Problem reasons: {inv['validation_errors'].replace('|', '; ')}")

                prop_names = ["(unassigned)"] + [p["name"] for p in properties]
                current_prop_name = "(unassigned)"
                if inv["property_id"]:
                    match = next((p for p in properties if p["id"] == inv["property_id"]), None)
                    if match:
                        current_prop_name = match["name"]

                with st.form(key=f"review_form_{selected_id}"):
                    property_choice = st.selectbox(
                        label_with_confidence("property_id", "Property"), prop_names,
                        index=prop_names.index(current_prop_name) if current_prop_name in prop_names else 0,
                    )
                    category = st.selectbox(
                        label_with_confidence("category", "Category"), CATEGORIES,
                        index=CATEGORIES.index(inv["category"]) if inv["category"] in CATEGORIES else 3,
                    )
                    vendor = st.text_input(label_with_confidence("vendor", "Vendor"), inv["vendor"] or "")
                    invoice_number = st.text_input(
                        label_with_confidence("invoice_number", "Invoice number"), inv["invoice_number"] or ""
                    )
                    c1, c2 = st.columns(2)
                    billing_start = c1.text_input(
                        label_with_confidence("billing_start", "Billing start (YYYY-MM-DD)"),
                        inv["billing_start"] or ""
                    )
                    billing_end = c2.text_input(
                        label_with_confidence("billing_end", "Billing end (YYYY-MM-DD)"),
                        inv["billing_end"] or ""
                    )
                    c3, c4 = st.columns(2)
                    consumption = c3.number_input(
                        label_with_confidence("consumption", "Consumption"),
                        value=float(inv["consumption"] or 0.0), step=1.0
                    )
                    consumption_unit = c4.text_input(
                        label_with_confidence("consumption_unit", "Unit"), inv["consumption_unit"] or ""
                    )
                    c5, c6 = st.columns(2)
                    taxes_fees = c5.number_input("Taxes/fees ($)", value=float(inv["taxes_fees"] or 0.0), step=1.0)
                    total_cost = c6.number_input(
                        label_with_confidence("total_cost", "Total cost ($)"),
                        value=float(inv["total_cost"] or 0.0), step=1.0
                    )
                    notes = st.text_area("Notes", inv["notes"] or "")

                    field_values = {
                        "property_id": None, "category": category, "vendor": vendor,
                        "invoice_number": invoice_number, "billing_start": billing_start,
                        "billing_end": billing_end, "consumption": consumption,
                        "consumption_unit": consumption_unit, "taxes_fees": taxes_fees,
                        "total_cost": total_cost, "notes": notes,
                    }
                    if property_choice != "(unassigned)":
                        field_values["property_id"] = next(p["id"] for p in properties if p["name"] == property_choice)

                    errors = validation.validate_invoice(field_values)
                    dupes = validation.find_logical_duplicates(conn, field_values, exclude_id=selected_id)

                    save_col, approve_col = st.columns(2)
                    save_clicked = save_col.form_submit_button("Save corrections")
                    approve_clicked = approve_col.form_submit_button(
                        "Approve and store", disabled=bool(errors) or (bool(dupes) and not inv["duplicate_override"])
                    )

                    if errors:
                        st.error("Cannot approve yet: " + "; ".join(errors))
                    override = inv["duplicate_override"]
                    if dupes and not inv["duplicate_override"]:
                        st.warning(f"Looks like a duplicate: {dupes[0]['reason']}")
                        override = st.checkbox("This is not a duplicate \u2014 override and allow approval")

                    if save_clicked or approve_clicked:
                        db.update_invoice(
                            conn, selected_id, field_values,
                            validation_errors=errors,
                            logical_duplicate_of=dupes[0]["invoice"]["id"] if dupes else None,
                            duplicate_override=override,
                            changed_by=operator_name(),
                        )
                        if approve_clicked and not errors:
                            db.approve_invoice(conn, selected_id, sf["id"], approved_by=operator_name())
                            st.success("Approved and stored in invoice history.")
                        else:
                            st.success("Corrections saved.")
                        st.rerun()


# ================================================================ ANALYSIS =
elif screen == "Analysis":
    st.header("Analysis")
    st.caption("Ad hoc lookup across any property/category/month. For a curated per-property "
               "view, use the Property screen.")

    properties = db.list_properties(conn)
    prop_names = [p["name"] for p in properties]
    col1, col2, col3 = st.columns(3)
    prop_choice = col1.selectbox("Property", prop_names)
    category_choice = col2.selectbox("Category", CATEGORIES)
    prop_id = next(p["id"] for p in properties if p["name"] == prop_choice)

    months = analysis.list_months_with_data(conn, prop_id, category_choice)
    if not months:
        st.caption(f"No approved {category_choice} invoices yet for {prop_choice}.")
    else:
        month_choice = col3.selectbox("Reporting month", list(reversed(months)))
        metrics = analysis.compute_property_month_metrics(conn, prop_id, category_choice, month_choice)
        if metrics:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total cost", f"${metrics['total_cost']:,.2f}")
            m2.metric("Cost / occupied unit",
                      f"${metrics['cost_per_occupied_unit']:,.2f}" if metrics['cost_per_occupied_unit'] else "\u2014")
            m3.metric("Usage / occupied unit / day",
                      f"{metrics['usage_per_unit_per_day']:.2f}" if metrics['usage_per_unit_per_day'] else "\u2014")
            m4.metric("Effective rate",
                      f"${metrics['effective_rate']:.4f}" if metrics['effective_rate'] else "\u2014")

            m5, m6, m7 = st.columns(3)
            m5.metric("YoY variance",
                      f"{metrics['yoy_variance_pct']:+.0f}%" if metrics['yoy_variance_pct'] is not None else "\u2014")
            m6.metric("Observed excess",
                      f"${metrics['observed_excess']:,.2f}" if metrics['observed_excess'] is not None else "\u2014")
            m7.metric("Baseline confidence", metrics["baseline_confidence"])

            st.info(metrics["explanation"])

        st.divider()
        rows = []
        for m in months[-24:]:
            met = analysis.compute_property_month_metrics(conn, prop_id, category_choice, m)
            if met:
                rows.append({"month": m, "Total cost": met["total_cost"]})
        if rows:
            st.subheader("24-month cost trend")
            st.line_chart(pd.DataFrame(rows).set_index("month"))


# ======================================================== FINDINGS & ACTIONS
elif screen == "Findings & Actions":
    st.header("Findings & Actions")
    tab_findings, tab_actions = st.tabs(["Findings", "Actions"])

    with tab_findings:
        status_filter = st.selectbox("Filter by status", ["All"] + FINDING_STATUSES)
        findings = db.list_findings(conn, status=None if status_filter == "All" else status_filter)

        if findings:
            for f in findings:
                sev_icon = {"High": "\U0001f534", "Medium": "\U0001f7e0", "Low": "\U0001f7e1"}.get(f["severity"], "\u26aa")
                with st.expander(f"{sev_icon} [{f['status']}] {f['description']} \u2014 "
                                 f"${(f['observed_excess'] or 0):,.0f}/yr"):
                    st.write(f"**Property:** {f['property_name']}  |  **Category:** {f['category']}")
                    st.write(f"**Evidence:** {f['evidence']}")
                    st.write(f"**Recommended action:** {f['recommended_action']}")
                    st.write(f"**Severity:** {f['severity']}  |  **Confidence:** {f['confidence']}  |  "
                             f"**Cause:** {f['cause']}")

                    new_status = st.selectbox(
                        "Status", FINDING_STATUSES, index=FINDING_STATUSES.index(f["status"]),
                        key=f"status_{f['id']}"
                    )
                    reason = None
                    if new_status == "Dismissed":
                        reason = st.text_input("Reason for dismissing", key=f"reason_{f['id']}")

                    action_col1, action_col2 = st.columns(2)
                    if action_col1.button("Save status", key=f"save_finding_{f['id']}"):
                        db.update_finding_status(conn, f["id"], new_status, dismissed_reason=reason)
                        st.rerun()

                    existing_actions = db.list_actions(conn, finding_id=f["id"])
                    if existing_actions:
                        st.caption(f"{len(existing_actions)} action(s) linked \u2014 see Actions tab.")
                    if action_col2.button("Add action", key=f"add_action_{f['id']}"):
                        st.session_state[f"show_action_form_{f['id']}"] = True

                    if st.session_state.get(f"show_action_form_{f['id']}"):
                        with st.form(key=f"action_form_{f['id']}"):
                            owner = st.text_input("Owner")
                            due_date = st.text_input("Due date (YYYY-MM-DD)")
                            expected_savings = st.number_input(
                                "Expected annual savings ($)", min_value=0.0, step=50.0,
                                value=float(f["observed_excess"] or 0)
                            )
                            notes = st.text_area("Notes")
                            if st.form_submit_button("Create action"):
                                db.insert_action(conn, f["id"], f["recommended_action"], owner=owner,
                                                  due_date=due_date, expected_savings=expected_savings, notes=notes)
                                st.success("Action created.")
                                st.session_state.pop(f"show_action_form_{f['id']}", None)
                                st.rerun()
        else:
            st.caption("No findings yet \u2014 confirm or investigate an incident from Triage.")

    with tab_actions:
        actions = db.list_actions(conn)
        if actions:
            status_filter2 = st.selectbox("Filter by action status", ["All"] + ACTION_STATUSES, key="action_status_filter")
            for a in actions:
                if status_filter2 != "All" and a["status"] != status_filter2:
                    continue
                with st.expander(f"[{a['status']}] {a['property_name']} \u2014 {a['action_taken']}"):
                    st.write(f"**Linked finding:** {a['finding_description']}")
                    st.write(f"**Owner:** {a['owner'] or '\u2014'}  |  **Due:** {a['due_date'] or '\u2014'}")
                    st.write(f"**Expected savings:** ${(a['expected_savings'] or 0):,.0f}")
                    if a["confirmed_savings"] is not None:
                        st.write(f"**Confirmed savings:** ${a['confirmed_savings']:,.0f}")
                    if a["notes"]:
                        st.write(f"**Notes:** {a['notes']}")

                    new_status = st.selectbox("Status", ACTION_STATUSES,
                                               index=ACTION_STATUSES.index(a["status"]) if a["status"] in ACTION_STATUSES else 0,
                                               key=f"action_status_{a['id']}")
                    confirmed = st.number_input("Confirmed savings ($, once resolved)", min_value=0.0, step=50.0,
                                                 value=float(a["confirmed_savings"] or 0), key=f"confirmed_{a['id']}")
                    notes_update = st.text_area("Update notes", a["notes"] or "", key=f"notes_{a['id']}")
                    if st.button("Save", key=f"save_action_{a['id']}"):
                        db.update_action(conn, a["id"], status=new_status,
                                          confirmed_savings=confirmed if confirmed else None,
                                          notes=notes_update)
                        st.rerun()
        else:
            st.caption("No actions yet \u2014 create one from a finding or from Triage.")


# ================================================================ SETTINGS =
elif screen == "Settings":
    st.header("Settings")

    tab_props, tab_occ, tab_thresholds, tab_safety, tab_audit = st.tabs(
        ["Properties", "Occupancy", "Anomaly thresholds", "Data safety", "Audit log"]
    )

    with tab_props:
        properties = db.list_properties(conn)
        if properties:
            st.dataframe(pd.DataFrame([dict(p) for p in properties]), width="stretch")
        with st.form("add_property_form"):
            st.write("Add a property")
            name = st.text_input("Name")
            address = st.text_input("Address")
            units = st.number_input("Units", min_value=0, step=1)
            sqft = st.number_input("Square footage", min_value=0, step=100)
            year = st.number_input("Construction year", min_value=1800, max_value=2100, step=1, value=2000)
            heating = st.text_input("Heating type")
            metering = st.selectbox("Metering arrangement",
                                     ["Individually metered", "Master-metered", "Mixed", "Unknown"])
            if st.form_submit_button("Add property") and name:
                db.add_property(conn, name, address, int(units), int(sqft), int(year), heating, metering)
                st.success(f"Added {name}")
                st.rerun()

    with tab_occ:
        properties = db.list_properties(conn)
        st.write("Import occupancy from CSV/Excel (columns: property, month, occupied_units, vacant_units)")
        occ_file = st.file_uploader("Occupancy file", type=["csv", "xlsx", "xls"], key="occ_upload")
        if occ_file:
            df_occ = extraction.read_tabular_file(occ_file.read(), occ_file.name)
            df_occ.columns = [c.strip().lower() for c in df_occ.columns]
            st.write("Preview:")
            st.dataframe(df_occ.head(10))

            preview_rows = []
            for _, row in df_occ.iterrows():
                prop_match = next((p for p in properties if p["name"].lower() == str(row.get("property", "")).lower()), None)
                occupied = int(row.get("occupied_units", 0) or 0)
                vacant = int(row.get("vacant_units", 0) or 0)
                valid = prop_match is not None and (not prop_match["units"] or (occupied + vacant) <= prop_match["units"])
                preview_rows.append({
                    "Property": row.get("property", ""), "Month": row.get("month", ""),
                    "Occupied": occupied, "Vacant": vacant,
                    "Valid": "\u2705" if valid else "\u274c",
                })
            st.write("Validation summary:")
            st.dataframe(pd.DataFrame(preview_rows), width="stretch")

            if st.button("Import occupancy rows"):
                imported, skipped = 0, 0
                for _, row in df_occ.iterrows():
                    prop_match = next((p for p in properties if p["name"].lower() == str(row.get("property", "")).lower()), None)
                    if not prop_match:
                        skipped += 1
                        continue
                    occupied = int(row.get("occupied_units", 0) or 0)
                    vacant = int(row.get("vacant_units", 0) or 0)
                    if prop_match["units"] and (occupied + vacant) > prop_match["units"]:
                        skipped += 1
                        continue
                    db.upsert_occupancy(conn, prop_match["id"], str(row.get("month", "")), occupied, vacant)
                    imported += 1
                st.success(f"Imported {imported} rows, skipped {skipped}.")

        st.divider()
        st.write("Or enter a single month manually")
        if properties:
            with st.form("occupancy_form"):
                prop_choice = st.selectbox("Property", [p["name"] for p in properties])
                month = st.text_input("Month (YYYY-MM)")
                occupied = st.number_input("Occupied units", min_value=0, step=1)
                vacant = st.number_input("Vacant units", min_value=0, step=1)
                if st.form_submit_button("Save occupancy") and month:
                    prop = next(p for p in properties if p["name"] == prop_choice)
                    if prop["units"] and (occupied + vacant) > prop["units"]:
                        st.error(f"Occupied + vacant ({occupied + vacant}) exceeds total units ({prop['units']}).")
                    else:
                        db.upsert_occupancy(conn, prop["id"], month, int(occupied), int(vacant))
                        st.success("Saved.")
                        st.rerun()
            occ = db.list_occupancy(conn)
            if occ:
                st.dataframe(pd.DataFrame([dict(o) for o in occ]), width="stretch")
        else:
            st.caption("Add a property first.")

    with tab_thresholds:
        st.write("Anomaly Rules V1 thresholds \u2014 edited here, applied everywhere without a code change.")
        settings = db.get_all_settings(conn)
        with st.form("thresholds_form"):
            yoy = st.number_input("Year-over-year cost increase (%)", value=float(settings.get("threshold_yoy_pct", 15)))
            usage = st.number_input("Usage per occupied unit above baseline (%)", value=float(settings.get("threshold_usage_pct", 20)))
            rate = st.number_input("Effective rate above baseline (%)", value=float(settings.get("threshold_rate_pct", 10)))
            sustained = st.number_input("Sustained condition (consecutive months)", value=int(settings.get("threshold_sustained_months", 2)), step=1)
            stddev = st.number_input("Standard deviations above history", value=float(settings.get("threshold_stddev", 2)))
            if st.form_submit_button("Save thresholds"):
                db.set_setting(conn, "threshold_yoy_pct", yoy)
                db.set_setting(conn, "threshold_usage_pct", usage)
                db.set_setting(conn, "threshold_rate_pct", rate)
                db.set_setting(conn, "threshold_sustained_months", int(sustained))
                db.set_setting(conn, "threshold_stddev", stddev)
                st.success("Thresholds saved.")
                st.session_state.pop("triaged_incidents", None)

    with tab_safety:
        st.write("Backup, restore, and export \u2014 an upgrade should never silently lose data.")
        if st.button("Create backup now"):
            dest = db.DATA_DIR / f"backup_{db.now_iso().replace(':', '-')}.db"
            db.backup_db(str(dest))
            st.success(f"Backup written to {dest}")

        st.download_button(
            "Export all structured data (CSV zip)", data=db.export_all_csv_zip(),
            file_name="invoice_review_export.zip", mime="application/zip",
        )

        st.divider()
        findings = db.list_findings(conn)
        month_for_report = st.text_input("Report month filter (YYYY-MM, optional)", key="report_month")
        if findings:
            md = reporting.generate_markdown(findings, month=month_for_report or None)
            csv_out = reporting.generate_csv(findings, month=month_for_report or None)
            pdf_out = reporting.generate_pdf(findings, month=month_for_report or None)
            r1, r2, r3 = st.columns(3)
            r1.download_button("Download Markdown", md, "monthly_action_report.md", "text/markdown")
            r2.download_button("Download CSV", csv_out, "monthly_action_report.csv", "text/csv")
            r3.download_button("Download PDF", pdf_out, "monthly_action_report.pdf", "application/pdf")
        else:
            st.caption("No findings yet \u2014 generate a report once findings exist.")

    with tab_audit:
        st.write("Every invoice field change and approval, with who made it.")
        log = db.list_audit_log(conn)
        if log:
            df_log = pd.DataFrame([dict(l) for l in log])
            st.dataframe(df_log, width="stretch")
        else:
            st.caption("No changes logged yet.")
