from sqlalchemy import Engine
from sqlalchemy.orm import Session

from src.models import Base
from src.models.profile import Profile

from .engine import engine


def init_db(bind: Engine | None = None) -> None:
    target = bind if bind is not None else engine
    Base.metadata.create_all(bind=target)
    with Session(target) as db:
        if db.get(Profile, 1) is None:
            db.add(Profile(id=1, full_name="Your Name", email="you@example.com"))
            db.commit()
