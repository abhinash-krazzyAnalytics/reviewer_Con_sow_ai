"""Generate sample policy + correct/incorrect SOWs in .md, .docx and .pdf.

Content is defined once as blocks and rendered to all three formats.
Run:  python setup_samples.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent / "sample_docs"

# block types: ("h1", text) ("h2", text) ("p", text) ("bullets", [text]) ("table", [[header...], [row...]])
POLICY = [
    ("h1", "Company SOW Policy (Sample)"),
    ("p", "Every Statement of Work must contain the seven sections below before it is signed."),
    ("h2", "1. Mandatory sections"),
    ("bullets", [
        "Project Scope & Objectives: define both In-Scope and Out-of-Scope boundaries.",
        "Deliverables Schedule: a table with ID, Deliverable, Format, Target Date and Owner.",
        "Acceptance Criteria & Sign-Off: measurable done metrics per deliverable and a review window with deemed acceptance.",
        "Roles & Responsibilities (RACI): Vendor vs Client responsibilities and named key leads.",
        "Commercials & Payment Milestones: total contract value, milestone billing triggers and payment terms.",
        "Assumptions & Dependencies: client environment and data access, and what happens if dates slip.",
        "Change Control Process: formal written change requests for scope, schedule or cost changes.",
    ]),
    ("h2", "2. Prohibited wording"),
    ("bullets", [
        "Subjective acceptance wording and open-ended client requirements.",
        "Uncapped revisions or maintenance on a fixed-fee contract.",
        "Vague obligations such as best efforts.",
        "Undefined dates such as TBD.",
    ]),
]

CORRECT = [
    ("h1", "Statement of Work: Customer Support Chatbot"),
    ("p", "This SOW is between Acme Analytics (the Vendor) and Northwind Retail (the Client)."),
    ("h2", "1. Project Scope & Objectives"),
    ("p", "In-Scope: design, build and deploy a customer support chatbot for order-status and returns questions, "
          "with an admin web UI for prompt management."),
    ("p", "Out-of-Scope: voice channels, languages other than English, integration with the Client's legacy CRM, "
          "and any hosting or support after the 30-day warranty period."),
    ("h2", "2. Deliverables Schedule"),
    ("table", [["ID", "Deliverable", "Format", "Target Date", "Owner"],
               ["D1", "Requirements document", "PDF", "2026-01-16", "Vendor Delivery Lead"],
               ["D2", "Chatbot prototype", "Hosted demo", "2026-02-13", "Vendor Data Scientist"],
               ["D3", "Production chatbot and admin UI", "Deployed application", "2026-03-27", "Vendor Delivery Lead"]]),
    ("h2", "3. Acceptance Criteria & Sign-Off"),
    ("bullets", [
        "D1 is accepted when the Client Product Owner approves the requirements in writing.",
        "D2 is accepted when intent accuracy is at least 90 percent on the agreed 500-sample test set.",
        "D3 is accepted when D2 criteria are met in production and the admin UI passes the agreed test checklist.",
    ]),
    ("p", "The Client has five (5) business days to review each deliverable. If no written feedback is received "
          "within that window, the deliverable is deemed accepted. Up to two (2) revision rounds per deliverable are included."),
    ("h2", "4. Roles & Responsibilities (RACI)"),
    ("p", "Key leads: Vendor Delivery Lead is Asha Verma. Client Product Owner is Daniel Cho."),
    ("table", [["Activity", "Responsible", "Accountable", "Consulted"],
               ["Requirements", "Vendor", "Client Product Owner", "Client Support Team"],
               ["Model build and testing", "Vendor", "Vendor Delivery Lead", "Client Product Owner"],
               ["Test data and system access", "Client IT", "Client Product Owner", "Vendor"],
               ["Acceptance testing", "Client Support Team", "Client Product Owner", "Vendor"]]),
    ("h2", "5. Commercials & Payment Milestones"),
    ("p", "The total contract value (TCV) is USD 120,000 on a fixed-fee basis."),
    ("table", [["Milestone", "Billing trigger", "Amount (USD)"],
               ["M1", "Acceptance of D1", "30,000"],
               ["M2", "Acceptance of D2", "40,000"],
               ["M3", "Acceptance of D3", "50,000"]]),
    ("p", "Invoices are payable Net 30 from the invoice date."),
    ("h2", "6. Assumptions & Dependencies"),
    ("bullets", [
        "The Client provides read access to the order system and 12 months of anonymised support tickets by 2026-01-09.",
        "The Client Product Owner is available for weekly reviews.",
        "If a dependency is late, the affected target dates move by the same number of days.",
    ]),
    ("h2", "7. Change Control Process"),
    ("p", "Any change to scope, schedule or cost requires a written Change Request (CR) signed by both parties "
          "before work on the change begins. The Vendor will provide an impact assessment within five (5) business days."),
]

INCORRECT = [
    ("h1", "Statement of Work: Customer Support Chatbot"),
    ("p", "This SOW is between Acme Analytics (the Vendor) and Northwind Retail (the Client)."),
    ("h2", "1. Project Scope"),
    ("p", "The Vendor will build a customer support chatbot and a web UI for the Client. "
          "Unlimited revisions to the chatbot prompts and UI are included in the fixed fee."),
    ("h2", "2. Deliverables"),
    ("table", [["ID", "Deliverable", "Format", "Target Date"],
               ["D1", "Requirements document", "PDF", "TBD"],
               ["D2", "Chatbot prototype", "Hosted demo", "TBD"],
               ["D3", "Production chatbot and UI", "Deployed application", "TBD"]]),
    ("h2", "3. Delivery Approach"),
    ("p", "The Vendor will deliver in iterations. Each deliverable is considered complete once it is "
          "approved to the Client's full satisfaction."),
    ("h2", "4. Commercials & Payment"),
    ("p", "The total contract value (TCV) is USD 120,000 on a fixed-fee basis. 50 percent is billed at project start "
          "and 50 percent on completion. Invoices are payable Net 30."),
]


def to_md(blocks) -> str:
    out = []
    for kind, val in blocks:
        if kind == "h1":
            out.append(f"# {val}")
        elif kind == "h2":
            out.append(f"## {val}")
        elif kind == "p":
            out.append(val)
        elif kind == "bullets":
            out.append("\n".join(f"- {b}" for b in val))
        elif kind == "table":
            lines = ["| " + " | ".join(val[0]) + " |", "|" + "|".join(["---"] * len(val[0])) + "|"]
            lines += ["| " + " | ".join(r) + " |" for r in val[1:]]
            out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


def to_docx(blocks, path):
    from docx import Document
    doc = Document()
    for kind, val in blocks:
        if kind == "h1":
            doc.add_heading(val, level=1)
        elif kind == "h2":
            doc.add_heading(val, level=2)
        elif kind == "p":
            doc.add_paragraph(val)
        elif kind == "bullets":
            for b in val:
                doc.add_paragraph(b, style="List Bullet")
        elif kind == "table":
            t = doc.add_table(rows=len(val), cols=len(val[0]), style="Table Grid")
            for i, row in enumerate(val):
                for j, cell in enumerate(row):
                    t.cell(i, j).text = cell
            doc.add_paragraph()
    doc.save(path)


def to_pdf(blocks, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    story = []
    for kind, val in blocks:
        if kind == "h1":
            story.append(Paragraph(escape(val), styles["Heading1"]))
        elif kind == "h2":
            story.append(Paragraph(escape(val), styles["Heading2"]))
        elif kind == "p":
            story += [Paragraph(escape(val), styles["Normal"]), Spacer(1, 6)]
        elif kind == "bullets":
            for b in val:
                story.append(Paragraph("&bull; " + escape(b), styles["Normal"]))
            story.append(Spacer(1, 6))
        elif kind == "table":
            data = [[Paragraph(escape(c), styles["Normal"]) for c in row] for row in val]
            t = Table(data, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [t, Spacer(1, 8)]
    SimpleDocTemplate(str(path), pagesize=letter).build(story)


def main():
    OUT.mkdir(exist_ok=True)
    for name, blocks in [("company_sow_policy", POLICY), ("correct_sow_sample", CORRECT),
                         ("incorrect_sow_sample", INCORRECT)]:
        (OUT / f"{name}.md").write_text(to_md(blocks), encoding="utf-8")
        to_docx(blocks, OUT / f"{name}.docx")
        to_pdf(blocks, OUT / f"{name}.pdf")
        print("created", name, "(.md .docx .pdf)")


if __name__ == "__main__":
    main()
