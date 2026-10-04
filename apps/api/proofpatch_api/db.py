"""SQLite persistence for run metadata and run events.

Large logs/diffs are never stored in the database -- only artifact paths, so a
dashboard can reconnect and reconstruct full history from small rows.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        # Ensure the containing directory exists for sqlite:///./path/db.sqlite
        raw = url.split("///", 1)[-1]
        if raw and raw != ":memory:":
            from pathlib import Path

            Path(raw).parent.mkdir(parents=True, exist_ok=True)
    return engine


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    # Import models so they are registered on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def session_scope():
    """Context manager producing a session that always closes."""

    from contextlib import contextmanager

    @contextmanager
    def _scope():
        session = get_session_factory()()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _scope()
