import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import get_session
from src.models import Base
from src.models.profile import Profile
from src.web.app import app

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    # StaticPool forces all connections (including from FastAPI's threadpool) to
    # share the same underlying SQLite connection, so in-memory tables are visible
    # across threads.
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    # Seed the required Profile(id=1)
    session.add(Profile(id=1, full_name="Test User", email="test@example.com"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session, monkeypatch) -> TestClient:
    def override_get_session():
        yield db_session

    # TestClient executes BackgroundTasks after each response. The real task
    # runners open src.db.engine.SessionLocal (the on-disk data/bespoke.db),
    # so route tests must never run them — they'd leak outside the in-memory
    # fixture db. Tests that assert on scheduling re-patch these themselves.
    monkeypatch.setattr("src.web.routes.tailor._run_analysis_sync", lambda sid: None)
    monkeypatch.setattr("src.web.routes.tailor._run_generation_sync", lambda sid: None)
    monkeypatch.setattr("src.web.routes.tailor._run_cover_letter_sync", lambda sid: None)
    # The app lifespan calls init_db() against the real on-disk engine; tests
    # must not create or touch data/bespoke.db.
    monkeypatch.setattr("src.web.app.init_db", lambda: None)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
