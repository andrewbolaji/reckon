"""Dialect tests for the loader's SQL builders (no DB connection needed)."""

from ingest.loader import _partition_delete_sql, _raw_table_ddl

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


# --- Partition delete: the backfill path --------------------------------


def test_partition_delete_targets_the_quoted_raw_schema():
    sql = _partition_delete_sql("aria_calls", "timestamp")
    assert 'DELETE FROM "raw".aria_calls' in sql


def test_partition_delete_quotes_the_date_column():
    # `timestamp` is a type name as well as a column name in both engines, so
    # an unquoted reference is a parse hazard.
    assert 'substring("timestamp", 1, 10)' in _partition_delete_sql("t", "timestamp")


def test_partition_delete_compares_the_date_prefix_not_a_cast():
    # Raw columns are text. Casting would fail the whole delete on one
    # unparseable row, and Redshift and Postgres disagree about that cast.
    sql = _partition_delete_sql("jobs", "scheduled_at")
    assert "BETWEEN %s AND %s" in sql
    for cast in ("::date", "CAST(", "to_date"):
        assert cast not in sql


def test_partition_delete_is_parameterised():
    # Window bounds are bound values, never interpolated into the statement.
    sql = _partition_delete_sql("stripe_payments", "timestamp")
    assert sql.count("%s") == 2
    assert "2026" not in sql
