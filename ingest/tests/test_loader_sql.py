"""Dialect tests for the raw-table DDL builder (no DB connection needed)."""

from ingest.loader import _raw_table_ddl

COLUMNS = ["call_id", "duration_seconds"]


def test_schema_is_quoted_reserved_word():
    # "raw" is a Redshift reserved word and must be double-quoted in every dialect.
    for wh in ("redshift", "postgres"):
        assert '"raw".aria_calls' in _raw_table_ddl("aria_calls", COLUMNS, wh)


def test_redshift_ddl_uses_getdate_and_varchar():
    ddl = _raw_table_ddl("aria_calls", COLUMNS, "redshift")
    assert 'CREATE TABLE IF NOT EXISTS "raw".aria_calls' in ddl
    assert "VARCHAR(65535)" in ddl
    assert "DEFAULT GETDATE()" in ddl
    # Postgres-isms that Redshift rejects must be absent
    assert "TEXT" not in ddl
    assert "now()" not in ddl


def test_postgres_ddl_uses_now_and_text():
    ddl = _raw_table_ddl("aria_calls", COLUMNS, "postgres")
    assert "call_id TEXT" in ddl
    assert "duration_seconds TEXT" in ddl
    assert "DEFAULT now()" in ddl
    assert "GETDATE" not in ddl


def test_unknown_type_falls_back_to_postgres():
    assert _raw_table_ddl("t", ["c"], "duckdb") == _raw_table_ddl("t", ["c"], "postgres")


def test_all_columns_present():
    ddl = _raw_table_ddl("jobs", ["job_id", "status", "value"], "redshift")
    for col in ("job_id", "status", "value", "_loaded_at"):
        assert col in ddl
