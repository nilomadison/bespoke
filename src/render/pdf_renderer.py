"""Render a generated resume dict to a PDF byte stream.

Mirrors src.render.docx_renderer.render_to_docx in structure and output, but emits
PDF via ReportLab. ATS rules: single-column flow, no tables, Helvetica family
(the PDF-safe substitute for Calibri), 0.75" margins.
"""
import io

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


def render_to_pdf(generated: dict, profile: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"Resume — {profile.get('full_name', '')}",
    )

    name_style = ParagraphStyle(
        "Name", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER, spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "Contact", fontName="Helvetica", fontSize=10, alignment=TA_CENTER, spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "Section", fontName="Helvetica-Bold", fontSize=12, alignment=TA_LEFT,
        spaceBefore=10, spaceAfter=4, textColor="#222222",
    )
    body_style = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=11, alignment=TA_LEFT, leading=14, spaceAfter=4,
    )
    item_head_style = ParagraphStyle(
        "ItemHead", fontName="Helvetica-Bold", fontSize=11, alignment=TA_LEFT, spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "Bullet", fontName="Helvetica", fontSize=11, alignment=TA_LEFT, leading=14,
        leftIndent=10, spaceAfter=2,
    )

    story = []

    name = profile.get("full_name") or ""
    if name:
        story.append(Paragraph(_escape(name), name_style))

    contact_parts = [
        profile.get("email"),
        profile.get("phone"),
        profile.get("location"),
        profile.get("linkedin_url"),
    ]
    contact_line = "  |  ".join(_escape(p) for p in contact_parts if p)
    if contact_line:
        story.append(Paragraph(contact_line, contact_style))

    if generated.get("summary"):
        story.append(Paragraph("Summary", section_style))
        story.append(Paragraph(_escape(generated["summary"]), body_style))

    if generated.get("skills"):
        story.append(Paragraph("Skills", section_style))
        story.append(Paragraph(_escape(generated["skills"]), body_style))

    if generated.get("experience"):
        story.append(Paragraph("Experience", section_style))
        for exp in generated["experience"]:
            head_left = f"{_escape(exp.get('title', ''))} — {_escape(exp.get('company', ''))}"
            dates = exp.get("dates") or ""
            if dates:
                head = f"{head_left}<font size='9' color='#777777'>   {_escape(dates)}</font>"
            else:
                head = head_left
            story.append(Paragraph(head, item_head_style))

            bullets = exp.get("bullets") or []
            if bullets:
                items = [
                    ListItem(Paragraph(_escape(b), bullet_style), leftIndent=12)
                    for b in bullets if b
                ]
                if items:
                    story.append(ListFlowable(items, bulletType="bullet", leftIndent=14))
            story.append(Spacer(1, 4))

    if generated.get("projects"):
        story.append(Paragraph("Projects", section_style))
        for proj in generated["projects"]:
            name_part = _escape(proj.get("name", ""))
            desc = proj.get("description") or ""
            text = f"<b>{name_part}</b>"
            if desc:
                text += f": {_escape(desc)}"
            story.append(Paragraph(text, body_style))

    if generated.get("education"):
        story.append(Paragraph("Education", section_style))
        for edu in generated["education"]:
            degree = _escape(edu.get("degree", ""))
            institution = _escape(edu.get("institution", ""))
            line = f"<b>{degree}</b> — {institution}"
            dates = edu.get("dates") or ""
            if dates:
                line += f" <font size='9' color='#777777'>{_escape(dates)}</font>"
            story.append(Paragraph(line, body_style))

    if generated.get("certifications"):
        story.append(Paragraph("Certifications", section_style))
        for cert in generated["certifications"]:
            line = f"<b>{_escape(cert.get('name', ''))}</b>"
            suffix_parts = [cert.get("issuer", ""), cert.get("year", "")]
            suffix = ", ".join(p for p in suffix_parts if p)
            if suffix:
                line += f" <font size='9' color='#777777'>({_escape(suffix)})</font>"
            story.append(Paragraph(line, body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _escape(text: str) -> str:
    """Escape for ReportLab paragraph mini-XML."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
