import enum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class TailoringStatus(str, enum.Enum):
    DRAFT = "draft"  # JD entered, analysis not yet started
    ANALYZING = "analyzing"  # stage 1 in progress (background task)
    ANALYZED = "analyzed"  # plan created, ready for human review
    PLAN_EDITED = "plan_edited"
    GENERATING = "generating"  # stage 2 in progress (background task)
    GENERATED = "generated"
    EXPORTED = "exported"


class TailoringSession(Base, TimestampMixin):
    __tablename__ = "tailoring_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TailoringStatus] = mapped_column(
        Enum(TailoringStatus), nullable=False, default=TailoringStatus.DRAFT
    )

    # Stage 1 outputs
    analysis_json: Mapped[dict | None] = mapped_column(JSON)
    analysis_prompt_version: Mapped[str | None] = mapped_column(String(16))

    # Stage 2 outputs (Milestone 3)
    generated_json: Mapped[dict | None] = mapped_column(JSON)
    generation_prompt_version: Mapped[str | None] = mapped_column(String(16))

    # Stage 3 outputs (Milestone 4) — cover letter
    cover_letter_json: Mapped[dict | None] = mapped_column(JSON)
    cover_letter_generating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Error state for background task failures
    error_message: Mapped[str | None] = mapped_column(Text)

    plan_items: Mapped[list["PlanItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PlanItem.sort_order",
    )


class PlanItemType(str, enum.Enum):
    JOB = "job"
    ACHIEVEMENT = "achievement"
    SKILL_GROUP = "skill_group"
    PROJECT = "project"
    EDUCATION = "education"
    CERTIFICATION = "certification"


class PlanItem(Base):
    __tablename__ = "plan_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("tailoring_session.id"), nullable=False, index=True
    )
    item_type: Mapped[PlanItemType] = mapped_column(Enum(PlanItemType), nullable=False)

    # Soft FK — can point to Achievement, Job, Project, Education, or Certification
    # No DB constraint because the target table varies by item_type
    reference_id: Mapped[int | None] = mapped_column(Integer)

    include: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    emphasis_note: Mapped[str | None] = mapped_column(Text)
    llm_rationale: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped["TailoringSession"] = relationship(back_populates="plan_items")
