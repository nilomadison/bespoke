"""Resolve PlanItem soft-FKs to display-friendly dicts for UI rendering."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.project import Project
from src.models.tailoring import PlanItem, PlanItemType


def resolve_items_for_display(items: list[PlanItem], db: Session) -> list[dict]:
    """Resolve each PlanItem's reference_id to human-readable text.

    Returns a list of dicts sorted by sort_order, ready for template rendering.
    Each dict has: id, type, reference_id, include, text, rationale, emphasis_note.
    """
    if not items:
        return []

    # Batch-load all referenced records to avoid N+1 queries
    job_ids = [i.reference_id for i in items if i.item_type == PlanItemType.JOB and i.reference_id]
    ach_ids = [
        i.reference_id for i in items if i.item_type == PlanItemType.ACHIEVEMENT and i.reference_id
    ]
    proj_ids = [
        i.reference_id for i in items if i.item_type == PlanItemType.PROJECT and i.reference_id
    ]
    edu_ids = [
        i.reference_id for i in items if i.item_type == PlanItemType.EDUCATION and i.reference_id
    ]
    cert_ids = [
        i.reference_id
        for i in items
        if i.item_type == PlanItemType.CERTIFICATION and i.reference_id
    ]

    jobs = (
        {j.id: j for j in db.scalars(select(Job).where(Job.id.in_(job_ids))).all()}
        if job_ids
        else {}
    )
    achs = (
        {a.id: a for a in db.scalars(select(Achievement).where(Achievement.id.in_(ach_ids))).all()}
        if ach_ids
        else {}
    )
    projs = (
        {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(proj_ids))).all()}
        if proj_ids
        else {}
    )
    edus = (
        {e.id: e for e in db.scalars(select(Education).where(Education.id.in_(edu_ids))).all()}
        if edu_ids
        else {}
    )
    certs = (
        {
            c.id: c
            for c in db.scalars(select(Certification).where(Certification.id.in_(cert_ids))).all()
        }
        if cert_ids
        else {}
    )

    resolved = []
    for item in sorted(items, key=lambda i: i.sort_order):
        text = None
        if item.item_type == PlanItemType.JOB:
            job = jobs.get(item.reference_id)
            if job:
                text = f"{job.title} at {job.company}"
        elif item.item_type == PlanItemType.ACHIEVEMENT:
            ach = achs.get(item.reference_id)
            if ach:
                text = ach.text
                if ach.metric:
                    text += f"  ({ach.metric})"
        elif item.item_type == PlanItemType.SKILL_GROUP:
            text = item.emphasis_note or "Skills"
        elif item.item_type == PlanItemType.PROJECT:
            proj = projs.get(item.reference_id)
            if proj:
                text = proj.name
        elif item.item_type == PlanItemType.EDUCATION:
            edu = edus.get(item.reference_id)
            if edu:
                text = f"{edu.degree} — {edu.institution}"
        elif item.item_type == PlanItemType.CERTIFICATION:
            cert = certs.get(item.reference_id)
            if cert:
                text = f"{cert.name} ({cert.issuer})"

        resolved.append(
            {
                "id": item.id,
                "type": item.item_type.value,
                "reference_id": item.reference_id,
                "include": item.include,
                "text": text,
                "rationale": item.llm_rationale,
                "emphasis_note": item.emphasis_note,
            }
        )

    return resolved
