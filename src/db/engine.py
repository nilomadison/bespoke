from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=settings.db_echo,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
