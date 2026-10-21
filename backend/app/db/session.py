from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None

_IN_MEMORY_SQLITE = {"sqlite://", "sqlite+pysqlite://", "sqlite:///:memory:"}


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def configure_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """(Re)create the process-wide engine and session factory."""
    global _engine, _factory
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        if url in _IN_MEMORY_SQLITE:
            kwargs.setdefault("poolclass", StaticPool)
    else:
        kwargs.setdefault("pool_pre_ping", True)
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    if _engine is not None:
        _engine.dispose()
    _engine = engine
    _factory = sessionmaker(engine, expire_on_commit=False)
    return engine


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _factory is None:
        configure_engine()
    assert _factory is not None
    return _factory


def get_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
