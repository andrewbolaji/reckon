"""Security tests: injection, privilege escalation, adversarial inputs."""

import json
import pytest
import psycopg2

from copilot.trust_gate import validate_sql
from copilot.tools import GENERIC_ERROR, tool_query_marts
from copilot.tests.conftest import requires_db


class TestSqlInjection:

    def test_semicolon_injection(self):
        ok, msg = validate_sql("SELECT 1 FROM marts.mart_revenue; DROP TABLE marts.mart_revenue")
        assert not ok
        assert "Multi-statement" in msg

    def test_union_to_raw_rejected(self):
        ok, msg = validate_sql(
            "SELECT revenue_dollars FROM marts.mart_revenue "
            "UNION SELECT call_id FROM raw.aria_calls"
        )
        assert not ok

    def test_subquery_to_raw_rejected(self):
        ok, msg = validate_sql(
            "SELECT * FROM marts.mart_revenue "
            "WHERE 1 = (SELECT count(*) FROM raw.aria_calls)"
        )
        assert not ok

    def test_subquery_to_staging_rejected(self):
        ok, msg = validate_sql(
            "SELECT * FROM marts.mart_revenue "
            "WHERE 1 = (SELECT count(*) FROM staging.stg_aria_calls)"
        )
        assert not ok

    def test_case_insensitive_drop(self):
        ok, _ = validate_sql("select * from marts.mart_revenue; dRoP table x")
        assert not ok

    def test_grant_rejected(self):
        ok, _ = validate_sql("GRANT ALL ON SCHEMA public TO public")
        assert not ok

    def test_copy_rejected(self):
        ok, _ = validate_sql("COPY marts.mart_revenue TO '/tmp/data.csv'")
        assert not ok


@requires_db
class TestReaderRoleEnforcement:

    def test_reader_cannot_write(self, reader_conn):
        """The reckon_reader role cannot insert into marts."""
        cur = reader_conn.cursor()
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            cur.execute(
                "INSERT INTO marts.mart_revenue (payment_date) VALUES ('2026-01-01')"
            )
        reader_conn.rollback()

    def test_reader_cannot_read_raw(self, reader_conn):
        """The reckon_reader role cannot access raw schema tables."""
        cur = reader_conn.cursor()
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM raw.aria_calls LIMIT 1")
        reader_conn.rollback()

    def test_reader_cannot_read_staging(self, reader_conn):
        """The reckon_reader role cannot access staging schema."""
        cur = reader_conn.cursor()
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM staging.stg_aria_calls LIMIT 1")
        reader_conn.rollback()

    def test_reader_can_read_marts(self, reader_conn):
        """The reckon_reader role can SELECT from marts."""
        cur = reader_conn.cursor()
        cur.execute("SELECT count(*) FROM marts.mart_revenue")
        rows = cur.fetchall()
        assert rows[0][0] >= 0

    def test_reader_cannot_drop(self, reader_conn):
        """The reckon_reader role cannot drop tables."""
        cur = reader_conn.cursor()
        with pytest.raises((psycopg2.errors.ReadOnlySqlTransaction, psycopg2.errors.InsufficientPrivilege)):
            cur.execute("DROP TABLE marts.mart_revenue")
        reader_conn.rollback()


@requires_db
class TestQueryMartsToolSecurity:

    def test_union_to_raw_blocked_at_db_level(self, admin_conn, reader_conn):
        """Even if the SQL validator misses it, the DB role blocks raw access."""
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT * FROM raw.aria_calls LIMIT 1",
        )
        assert "error" in result

    def test_tool_rejects_dml(self, admin_conn, reader_conn):
        result = tool_query_marts(
            admin_conn, reader_conn,
            "DELETE FROM marts.mart_revenue",
        )
        assert result["error"] == "query_rejected"

    def test_tool_logs_rejection(self, admin_conn, reader_conn, capsys):
        tool_query_marts(
            admin_conn, reader_conn,
            "DROP TABLE marts.mart_revenue",
        )
        captured = capsys.readouterr()
        assert "query_marts" in captured.err
        assert "rejected" in captured.err.lower() or "Forbidden" in captured.err


@requires_db
class TestErrorSanitization:

    def test_query_error_returns_generic_message(self, admin_conn, reader_conn):
        """A query that triggers a DB error returns a generic message, not raw internals."""
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT nonexistent_column FROM marts.mart_revenue",
        )
        assert result["error"] == "query_failed"
        assert result["message"] == GENERIC_ERROR
        assert "nonexistent_column" not in result["message"]
        assert "column" not in result["message"].lower()

    def test_query_error_logs_detail_to_stderr(self, admin_conn, reader_conn, capsys):
        """The real error detail goes to the audit log (stderr), not to the user."""
        tool_query_marts(
            admin_conn, reader_conn,
            "SELECT nonexistent_column FROM marts.mart_revenue",
        )
        captured = capsys.readouterr()
        log_line = captured.err.strip().split("\n")[-1]
        log = json.loads(log_line)
        assert "nonexistent_column" in log["error"]

    def test_error_result_has_no_sql(self, admin_conn, reader_conn):
        """Error results must not leak the SQL that was executed."""
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT nonexistent_column FROM marts.mart_revenue",
        )
        assert "sql" not in result
