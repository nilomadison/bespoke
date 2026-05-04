import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    CO_FOUNDER = "co_founder"


class Job(Base, TimestampMixin):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)  # NULL = current role
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType), nullable=False, default=EmploymentType.FULL_TIME
    )
    summary: Mapped[str | None] = mapped_column(Text)
    is_technical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    achievements: Mapped[list["Achievement"]] = relationship(  # noqa: F821
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Achievement.sort_order",
    )
    job_skills: Mapped[list["JobSkill"]] = relationship(  # noqa: F821
        back_populates="job",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list["Project"]] = relationship(back_populates="job")  # noqa: F821
