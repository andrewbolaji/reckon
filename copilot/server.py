"""MCP server for the Reckon copilot."""

import json

from mcp.server.fastmcp import FastMCP

from copilot.db import get_conn
from copilot.tools import (
    tool_call_funnel,
    tool_check_freshness,
    tool_describe_schema,
    tool_job_completion,
    tool_query_marts,
    tool_revenue_summary,
)

server = FastMCP(
    "Reckon Copilot",
    instructions=(
        "You are a business intelligence copilot for a home-services company. "
        "You answer questions using ONLY the data returned by your tools. "
        "Every number in your answer must come from a tool result. "
        "If a tool returns a 'data_stale' error, relay the refusal message "
        "to the user exactly -- do not guess or estimate. "
        "If a tool returns a 'caveat' field, include that caveat in your answer. "
        "If the data cannot answer the question, say so honestly. "
        "Do not invent, estimate, or hallucinate any numbers."
    ),
)


def _conns():
    """Return (admin_conn, reader_conn).

    admin_conn: full-privilege connection for freshness checks (reads raw schema).
    reader_conn: read-only reckon_reader role, restricted to marts schema.
    """
    return get_conn(read_only=False), get_conn(read_only=True)


@server.tool()
def check_freshness() -> str:
    """Check how recent the warehouse data is.

    Returns the last load time and freshness status for each data source
    (aria_calls, stripe_payments, jobs). Use this when the user asks
    about data recency, or before answering if you are unsure whether
    the data is current.
    """
    admin_conn = get_conn(read_only=False)
    try:
        result = tool_check_freshness(admin_conn)
        return json.dumps(result, default=str)
    finally:
        admin_conn.close()


@server.tool()
def revenue_summary(
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str | None = None,
) -> str:
    """Get revenue data from Stripe payments.

    Args:
        date_from: Start date filter (YYYY-MM-DD), optional.
        date_to: End date filter (YYYY-MM-DD), optional.
        group_by: How to group results. Options: "service" (by service type),
                  "date" (by day), or omit for a single summary row.

    Returns revenue_dollars, net_revenue_dollars, transaction_count,
    avg_ticket_dollars, and refund information. Every number comes from
    the marts.mart_revenue table.
    """
    admin_conn, reader_conn = _conns()
    try:
        freshness_cache: dict = {}
        result = tool_revenue_summary(
            admin_conn, reader_conn, date_from, date_to, group_by, freshness_cache
        )
        return json.dumps(result, default=str)
    finally:
        admin_conn.close()
        reader_conn.close()


@server.tool()
def call_funnel(
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Get call funnel metrics from Aria voice agent data.

    Args:
        date_from: Start date filter (YYYY-MM-DD), optional.
        date_to: End date filter (YYYY-MM-DD), optional.

    Returns total_calls, booked, booking_rate_pct, avg_sentiment,
    escalation_rate_pct, and job completion counts. Every number comes
    from the marts.mart_call_funnel table.
    """
    admin_conn, reader_conn = _conns()
    try:
        freshness_cache: dict = {}
        result = tool_call_funnel(
            admin_conn, reader_conn, date_from, date_to, freshness_cache
        )
        return json.dumps(result, default=str)
    finally:
        admin_conn.close()
        reader_conn.close()


@server.tool()
def job_completion(
    service_category: str | None = None,
) -> str:
    """Get job completion metrics.

    Args:
        service_category: Filter by service type (e.g. "plumbing repair"), optional.

    Returns total_jobs, completed, completion_rate_pct, and
    total_completed_value by service category. Every number comes from
    the marts.mart_jobs table.
    """
    admin_conn, reader_conn = _conns()
    try:
        freshness_cache: dict = {}
        result = tool_job_completion(
            admin_conn, reader_conn, service_category, freshness_cache
        )
        return json.dumps(result, default=str)
    finally:
        admin_conn.close()
        reader_conn.close()


@server.tool()
def query_marts(sql: str) -> str:
    """Run a read-only SQL query against the marts tables.

    Use this only when the other tools (revenue_summary, call_funnel,
    job_completion) cannot answer the question. The query must be a
    single SELECT statement that references only these tables:
    marts.mart_call_funnel, marts.mart_revenue, marts.mart_jobs.

    Args:
        sql: A SELECT query. No DDL, DML, or multi-statement input.
             Maximum 100 rows returned. 5-second timeout.

    The query is validated, logged, and executed with a read-only
    database role that can only SELECT from the marts schema.
    """
    admin_conn, reader_conn = _conns()
    try:
        freshness_cache: dict = {}
        result = tool_query_marts(
            admin_conn, reader_conn, sql, freshness_cache
        )
        return json.dumps(result, default=str)
    finally:
        admin_conn.close()
        reader_conn.close()


@server.tool()
def describe_schema() -> str:
    """Get the schema of all available mart tables.

    Returns table names, column names, column types, and descriptions
    for marts.mart_call_funnel, marts.mart_revenue, and marts.mart_jobs.
    Use this to understand what data is available before writing a query.
    """
    result = tool_describe_schema()
    return json.dumps(result, default=str)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
