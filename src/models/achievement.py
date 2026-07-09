from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Achievement(Base, TimestampMixin):
    __tablename__ = "achievement"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), nullable=False, index=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str | None] = mapped_column(String(500))

    # JSON list of strings e.g. ["cost_reduction", "leadership", "scale"]
    impact_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    job: Mapped["Job"] = relationship(back_populates="achievements")  # noqa: F821
