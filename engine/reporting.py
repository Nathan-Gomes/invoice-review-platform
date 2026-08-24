"""
reporting.py — Generates the Monthly Action Report from approved findings only,
in Markdown, CSV, and printable PDF. The report must exactly match what's
visible in the Findings screen for the selected month/status — no silent
extra filtering.
"""

import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch


COLUMNS = ["property_name", "description", "evidence", "observed_excess",
           "recommended_action", "severity", "status"]
HEADERS = ["Property", "Finding", "Evidence", "Annual Impact",
           "Recommended Action", "Severity", "Status"]


def _rows_for_report(findings, month=None, statuses=None):
    """
    findings: list of sqlite3.Row / dict from db.list_findings().
    month: optional 'YYYY-MM' to filter by created_at prefix.
    statuses: optional list of statuses to include (default: everything except Dismissed).
    """
    out = []
    for f in findings:
        d = dict(f)
        if statuses and d["status"] not in statuses:
            continue
        if not statuses and d["status"] == "Dismissed":
            continue
        if month and not (d.get("created_at") or "").startswith(month):
            continue
        out.append(d)
    return out


def generate_markdown(findings, month=None, statuses=None, title="Monthly Action Report"):
    rows = _rows_for_report(findings, month, statuses)
    lines = [f"# {title}\n"]
    if month:
        lines.append(f"_Reporting month: {month}_\n")
    lines.append("| Property | Finding | Evidence | Annual Impact | Recommended Action | Severity | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        impact = f"${r['observed_excess']:,.0f}" if r.get("observed_excess") is not None else "—"
        lines.append(
            f"| {r.get('property_name','')} | {r.get('description','')} | {r.get('evidence','')} | "
            f"{impact} | {r.get('recommended_action','')} | {r.get('severity','')} | {r.get('status','')} |"
        )
    if not rows:
        lines.append("| _No findings match this filter._ | | | | | | |")
    return "\n".join(lines)


def generate_csv(findings, month=None, statuses=None):
    import csv as csv_module
    rows = _rows_for_report(findings, month, statuses)
    out = io.StringIO()
    writer = csv_module.writer(out)
    writer.writerow(HEADERS)
    for r in rows:
        impact = f"{r['observed_excess']:.2f}" if r.get("observed_excess") is not None else ""
        writer.writerow([
            r.get("property_name", ""), r.get("description", ""), r.get("evidence", ""),
            impact, r.get("recommended_action", ""), r.get("severity", ""), r.get("status", ""),
        ])
    return out.getvalue()


def generate_pdf(findings, month=None, statuses=None, title="Monthly Action Report"):
    rows = _rows_for_report(findings, month, statuses)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"])]
    if month:
        story.append(Paragraph(f"Reporting month: {month}", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    table_data = [["Property", "Finding", "Evidence", "Impact", "Action", "Sev.", "Status"]]
    for r in rows:
        impact = f"${r['observed_excess']:,.0f}" if r.get("observed_excess") is not None else "—"
        table_data.append([
            Paragraph(str(r.get("property_name", "")), styles["Normal"]),
            Paragraph(str(r.get("description", "")), styles["Normal"]),
            Paragraph(str(r.get("evidence", "")), styles["Normal"]),
            impact,
            Paragraph(str(r.get("recommended_action", "")), styles["Normal"]),
            r.get("severity", ""),
            r.get("status", ""),
        ])
    if not rows:
        table_data.append(["No findings match this filter.", "", "", "", "", "", ""])

    col_widths = [0.9 * inch, 1.3 * inch, 1.6 * inch, 0.7 * inch, 1.5 * inch, 0.5 * inch, 0.7 * inch]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return buf.read()
