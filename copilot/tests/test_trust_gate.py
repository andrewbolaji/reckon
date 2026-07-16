"""Tests for the trust gate: freshness checking and SQL validation."""

import pytest

from copilot.trust_gate import check_freshness, validate_sql, apply_row_cap
from copilot.tests.conftest import requires_db


# --- Freshness tests (require DB) ---

@requires_db
class TestFreshness:

    def test_fresh_data_returns_fresh(self, admin_conn):
        """Data loaded recently should report as fresh."""
        result = check_freshness(admin_conn)
        assert result["fresh"] is True
        assert all(s["status"] == "fresh" for s in result["sources"])

    def test_stale_data_returns_error(self, admin_conn, force_stale):
        """Data older than 48h should report as error."""
        result = check_freshness(admin_conn)
        assert result["fresh"] is False
        assert "stale" in result["message"].lower()
        assert any(s["status"] == "error" for s in result["sources"])

    def test_warn_data_returns_warn(self, admin_conn, force_warn):
        """Data 24-48h old should report warn but still be fresh."""
        result = check_freshness(admin_conn)
        assert result["fresh"] is True
        assert result["warn"] is True
        assert "Note:" in result.get("message", "")

    def test_freshness_includes_all_sources(self, admin_conn):
        """Freshness check should cover all three sources."""
        result = check_freshness(admin_conn)
        names = {s["name"] for s in result["sources"]}
        assert names == {"aria_calls", "stripe_payments", "jobs"}


# --- SQL validation tests (no DB needed) ---

class TestSqlValidation:

    def test_select_allowed(self):
        ok, _ = validate_sql("SELECT * FROM marts.mart_revenue")
        assert ok

    def test_select_with_where(self):
        ok, _ = validate_sql(
            "SELECT revenue_dollars FROM marts.mart_revenue WHERE payment_date >= '2026-07-01'"
        )
        assert ok

    def test_ddl_drop_rejected(self):
        ok, msg = validate_sql("DROP TABLE marts.mart_revenue")
        assert not ok
        assert "SELECT" in msg or "Forbidden" in msg

    def test_ddl_create_rejected(self):
        ok, msg = validate_sql("CREATE TABLE foo (id int)")
        assert not ok

    def test_ddl_alter_rejected(self):
        ok, msg = validate_sql("ALTER TABLE marts.mart_revenue ADD COLUMN x int")
        assert not ok

    def test_dml_insert_rejected(self):
        ok, msg = validate_sql("INSERT INTO marts.mart_revenue VALUES (1)")
        assert not ok

    def test_dml_update_rejected(self):
        ok, msg = validate_sql("UPDATE marts.mart_revenue SET revenue_dollars = 0")
        assert not ok

    def test_dml_delete_rejected(self):
        ok, msg = validate_sql("DELETE FROM marts.mart_revenue")
        assert not ok

    def test_dml_truncate_rejected(self):
        ok, msg = validate_sql("TRUNCATE marts.mart_revenue")
        assert not ok

    def test_multi_statement_rejected(self):
        ok, msg = validate_sql("SELECT 1; DROP TABLE marts.mart_revenue")
        assert not ok
        assert "Multi-statement" in msg

    def test_raw_table_rejected(self):
        ok, msg = validate_sql("SELECT * FROM raw.aria_calls")
        assert not ok
        assert "raw" in msg.lower()

    def test_staging_table_rejected(self):
        ok, msg = validate_sql("SELECT * FROM staging.stg_aria_calls")
        assert not ok

    def test_pg_catalog_rejected(self):
        ok, msg = validate_sql("SELECT * FROM pg_catalog.pg_tables")
        assert not ok

    def test_information_schema_rejected(self):
        ok, msg = validate_sql("SELECT * FROM information_schema.tables")
        assert not ok

    def test_comment_wrapped_attack_rejected(self):
        ok, msg = validate_sql("/* harmless */ DROP TABLE marts.mart_revenue")
        assert not ok

    def test_line_comment_attack_rejected(self):
        ok, msg = validate_sql("-- just a comment\nDROP TABLE marts.mart_revenue")
        assert not ok

    def test_unknown_table_rejected(self):
        ok, msg = validate_sql("SELECT * FROM public.users")
        assert not ok
        assert "not allowed" in msg.lower()

    def test_empty_query_rejected(self):
        ok, msg = validate_sql("")
        assert not ok

    def test_whitespace_only_rejected(self):
        ok, msg = validate_sql("   ")
        assert not ok


class TestRowCap:

    def test_adds_limit_when_missing(self):
        result = apply_row_cap("SELECT * FROM marts.mart_revenue")
        assert "LIMIT 100" in result

    def test_preserves_limit_under_cap(self):
        result = apply_row_cap("SELECT * FROM marts.mart_revenue LIMIT 50")
        assert "LIMIT 50" in result

    def test_caps_limit_over_max(self):
        result = apply_row_cap("SELECT * FROM marts.mart_revenue LIMIT 500")
        assert "LIMIT 100" in result
        assert "500" not in result
