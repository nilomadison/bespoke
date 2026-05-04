from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    live_url: Mapped[str | None] = mapped_column(String(500))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prominence: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    job: Mapped["Job | None"] = relationship(back_populates="projects")  # noqa: F821
    project_skills: Mapped[list["ProjectSkill"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectSkill(Base):
    __tablename__ = "project_skill"

    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id"), primary_key=True)

    project: Mapped["Project"] = relationship(back_populates="project_skills")
    skill: Mapped["Skill"] = relationship(back_populates="project_skills")  # noqa: F821
