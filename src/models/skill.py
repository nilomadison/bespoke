from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str | None] = mapped_column(String(100))

    job_skills: Mapped[list["JobSkill"]] = relationship(back_populates="skill")
    project_skills: Mapped[list["ProjectSkill"]] = relationship(back_populates="skill")  # noqa: F821


class JobSkill(Base):
    __tablename__ = "job_skill"

    job_id: Mapped[int] = mapped_column(ForeignKey("job.id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id"), primary_key=True)
    proficiency: Mapped[str | None] = mapped_column(String(50))  # "expert", "proficient", "familiar"
    years_used: Mapped[float | None] = mapped_column(Float)

    job: Mapped["Job"] = relationship(back_populates="job_skills")  # noqa: F821
    skill: Mapped["Skill"] = relationship(back_populates="job_skills")
