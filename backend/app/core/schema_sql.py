"""DDL that SQLAlchemy metadata can't express. Used by migration 001 and by the test setup."""

PRE = [
    "CREATE EXTENSION IF NOT EXISTS postgis",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
]

POST = [
    "CREATE SEQUENCE IF NOT EXISTS sr_seq START 1001",
    "CREATE SEQUENCE IF NOT EXISTS wo_seq START 1001",
    """
    CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'table % is append-only (% blocked)', TG_TABLE_NAME, TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log",
    """CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
       FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""",
    "DROP TRIGGER IF EXISTS status_events_append_only ON status_events",
    """CREATE TRIGGER status_events_append_only BEFORE UPDATE OR DELETE ON status_events
       FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""",
    "CREATE INDEX IF NOT EXISTS ix_sr_description_trgm ON service_requests USING gin (description gin_trgm_ops)",
]
