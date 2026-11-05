from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  (register all tables)
from app.config import settings
from app.core.db import Base

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # PostGIS/tiger tables live in the same DB; never autogenerate against them.
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return True


def run_migrations_online() -> None:
    url = context.config.attributes.get("url") or settings.database_url
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
