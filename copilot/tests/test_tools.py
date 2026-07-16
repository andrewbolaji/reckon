"""Tests for tool correctness: outputs match direct warehouse queries."""

import pytest
from decimal import Decimal

from copilot.db import query
from copilot.tools import (
    tool_call_funnel,
    tool_check_freshness,
    tool_describe_schema,
    tool_job_completion,
    tool_query_marts,
    tool_revenue_summary,
)
from copilot.tests.conftest import requires_db


@requires_db
class TestRevenueSummary:

    def test_total_revenue_matches_direct_query(self, admin_conn, reader_conn):
        """Tool revenue matches SELECT sum(revenue_dollars) FROM marts.mart_revenue."""
        direct = query(
            reader_conn,
            "SELECT round(sum(revenue_dollars), 2) AS revenue_dollars FROM marts.mart_revenue",
        )
        tool_result = tool_revenue_summary(admin_conn, reader_conn)
        assert "data" in tool_result
        tool_revenue = tool_result["data"][0]["revenue_dollars"]
        assert Decimal(str(tool_revenue)) == Decimal(str(direct[0]["revenue_dollars"]))

    def test_by_service_returns_multiple_rows(self, admin_conn, reader_conn):
        result = tool_revenue_summary(admin_conn, reader_conn, group_by="service")
        assert result["row_count"] > 1

    def test_by_date_returns_sorted(self, admin_conn, reader_conn):
        result = tool_revenue_summary(admin_conn, reader_conn, group_by="date")
        dates = [r["payment_date"] for r in result["data"]]
        assert dates == sorted(dates)


@requires_db
class TestCallFunnel:

    def test_booking_rate_matches_direct_query(self, admin_conn, reader_conn):
        """Tool booking rate matches direct calculation."""
        direct = query(
            reader_conn,
            """
            SELECT round(100.0 * sum(booked) / nullif(sum(total_calls), 0), 1)
                AS booking_rate_pct
            FROM marts.mart_call_funnel
            """,
        )
        tool_result = tool_call_funnel(admin_conn, reader_conn)
        assert "data" in tool_result
        tool_rate = tool_result["data"][0]["booking_rate_pct"]
        assert Decimal(str(tool_rate)) == Decimal(str(direct[0]["booking_rate_pct"]))

    def test_total_calls_positive(self, admin_conn, reader_conn):
        result = tool_call_funnel(admin_conn, reader_conn)
        assert result["data"][0]["total_calls"] > 0


@requires_db
class TestJobCompletion:

    def test_completion_matches_direct_query(self, admin_conn, reader_conn):
        """Tool completion data matches direct query."""
        direct = query(
            reader_conn,
            """
            SELECT sum(total_jobs) AS total_jobs,
                   sum(completed) AS completed,
                   round(sum(total_completed_value), 2) AS total_completed_value
            FROM marts.mart_jobs
            """,
        )
        tool_result = tool_job_completion(admin_conn, reader_conn)
        total = sum(r["total_jobs"] for r in tool_result["data"])
        assert total == direct[0]["total_jobs"]

    def test_filter_by_service(self, admin_conn, reader_conn):
        all_result = tool_job_completion(admin_conn, reader_conn)
        if all_result["row_count"] > 0:
            first_service = all_result["data"][0]["service_category"]
            filtered = tool_job_completion(
                admin_conn, reader_conn, service_category=first_service
            )
            assert filtered["row_count"] == 1
            assert filtered["data"][0]["service_category"] == first_service


@requires_db
class TestQueryMarts:

    def test_valid_select_returns_data(self, admin_conn, reader_conn):
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT count(*) AS n FROM marts.mart_revenue",
        )
        assert "data" in result
        assert result["data"][0]["n"] > 0

    def test_sql_included_in_result(self, admin_conn, reader_conn):
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT count(*) AS n FROM marts.mart_revenue",
        )
        assert "sql" in result
        assert "mart_revenue" in result["sql"]


@requires_db
class TestStaleRefusal:

    def test_stale_revenue_refused(self, admin_conn, reader_conn, force_stale):
        result = tool_revenue_summary(admin_conn, reader_conn)
        assert result["error"] == "data_stale"
        assert "data" not in result

    def test_stale_call_funnel_refused(self, admin_conn, reader_conn, force_stale):
        result = tool_call_funnel(admin_conn, reader_conn)
        assert result["error"] == "data_stale"

    def test_stale_job_completion_refused(self, admin_conn, reader_conn, force_stale):
        result = tool_job_completion(admin_conn, reader_conn)
        assert result["error"] == "data_stale"

    def test_stale_query_marts_refused(self, admin_conn, reader_conn, force_stale):
        result = tool_query_marts(
            admin_conn, reader_conn,
            "SELECT * FROM marts.mart_revenue",
        )
        assert result["error"] == "data_stale"


@requires_db
class TestWarnCaveat:

    def test_warn_revenue_has_caveat(self, admin_conn, reader_conn, force_warn):
        result = tool_revenue_summary(admin_conn, reader_conn)
        assert "data" in result
        assert "caveat" in result
        assert "Note:" in result["caveat"]


class TestDescribeSchema:

    def test_returns_all_marts(self):
        result = tool_describe_schema()
        assert "tables" in result
        tables = result["tables"]
        assert "marts.mart_call_funnel" in tables
        assert "marts.mart_revenue" in tables
        assert "marts.mart_jobs" in tables

    def test_tables_have_columns(self):
        result = tool_describe_schema()
        for table_info in result["tables"].values():
            assert "columns" in table_info
            assert len(table_info["columns"]) > 0
            assert "description" in table_info
