from src.models import Base
from src.models.profile import Profile

from .engine import SessionLocal, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.get(Profile, 1) is None:
            db.add(Profile(id=1, full_name="Your Name", email="you@example.com"))
            db.commit()
    finally:
        db.close()
