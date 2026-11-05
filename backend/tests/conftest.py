import os

# Point the app at the test database BEFORE anything imports app.config.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://civicflow:civicflow@localhost:5432/civicflow_test"
)
os.environ["AGENT_MODE"] = "rules"
os.environ["SCHEDULER_ENABLED"] = "false"

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.core import db as dbmod  # noqa: E402
from app.core.bus import bus  # noqa: E402
from app.core.clock import IST, clock  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.schema_sql import POST, PRE  # noqa: E402

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=IST)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with dbmod.engine.begin() as conn:
        for s in PRE:
            conn.execute(text(s))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        for s in POST:
            conn.execute(text(s))
    yield


@pytest.fixture(autouse=True)
def _clean():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with dbmod.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    bus.sync = True
    bus.clear()
    clock.freeze(T0)
    yield
    clock.unfreeze()


@pytest.fixture
def db():
    s = dbmod.SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def world(db):
    from tests.factories import make_world

    w = make_world(db)
    db.commit()
    return w
