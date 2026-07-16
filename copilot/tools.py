"""MCP tool implementations for the Reckon copilot."""

import time

from copilot.audit import log_entry
from copilot.db import query
from copilot.trust_gate import (
    apply_row_cap,
    check_freshness,
    validate_sql,
)

SCHEMA_INFO = {
    "marts.mart_call_funnel": {
        "description": "Daily aggregation of Aria voice agent call metrics with job completion tracking.",
        "columns": {
            "call_date": "Date of calls (date)",
            "total_calls": "Count of all calls that day (int)",
            "qualified": "Calls with outcome 'qualified' (int)",
            "booked": "Calls with outcome 'booked' -- the key conversion metric (int)",
            "escalated": "Calls with outcome 'escalated' (int)",
            "missed": "Calls with outcome 'missed' (int)",
            "resolved": "Calls with outcome 'resolved' (int)",
            "avg_duration_seconds": "Mean call duration in seconds (numeric)",
            "avg_sentiment": "Mean sentiment score, 0.0 to 1.0 (numeric)",
            "booking_rate_pct": "100 * booked / total_calls (numeric)",
            "escalation_rate_pct": "100 * escalated / total_calls (numeric)",
            "miss_rate_pct": "100 * missed / total_calls (numeric)",
            "total_jobs": "Jobs related to booked calls that day (int)",
            "completed_jobs": "Jobs with status 'completed' (int)",
            "cancelled_jobs": "Jobs with status 'cancelled' (int)",
        },
    },
    "marts.mart_revenue": {
        "description": "Daily revenue aggregation from Stripe payments, broken down by service and payment method.",
        "columns": {
            "payment_date": "Date of payments (date)",
            "service_description": "Service type, e.g. plumbing repair, HVAC maintenance (text)",
            "payment_method": "Payment method: 'card' or 'ach' (text)",
            "transaction_count": "Number of transactions (int)",
            "revenue_dollars": "Gross revenue in dollars (numeric)",
            "avg_ticket_dollars": "Average transaction amount in dollars (numeric)",
            "refund_count": "Number of refunded transactions (int)",
            "refund_dollars": "Total refunded amount in dollars (numeric)",
            "net_revenue_dollars": "revenue_dollars minus refund_dollars (numeric)",
        },
    },
    "marts.mart_jobs": {
        "description": "Job completion metrics by service category.",
        "columns": {
            "service_category": "Service type (text)",
            "total_jobs": "Total jobs in this category (int)",
            "completed": "Jobs with status 'completed' (int)",
            "scheduled": "Jobs with status 'scheduled' (int)",
            "cancelled": "Jobs with status 'cancelled' (int)",
            "completion_rate_pct": "100 * completed / total_jobs (numeric)",
            "avg_completed_value": "Mean dollar value of completed jobs (numeric)",
            "total_completed_value": "Sum dollar value of completed jobs (numeric)",
        },
    },
}


def _gate(admin_conn, freshness_cache: dict | None = None) -> dict | None:
    """Check freshness using the admin connection (needs raw schema access).

    Returns a refusal dict if data is stale (error threshold), None if ok.
    Caches the result in freshness_cache to avoid repeated queries.
    """
    if freshness_cache and "result" in freshness_cache:
        result = freshness_cache["result"]
    else:
        result = check_freshness(admin_conn)
        if freshness_cache is not None:
            freshness_cache["result"] = result

    if not result["fresh"]:
        return {
            "error": "data_stale",
            "message": result["message"],
            "sources": result["sources"],
        }
    return None


def _caveat(freshness_cache: dict | None = None) -> str | None:
    """Return a data-age caveat string if any source is in warn state."""
    if freshness_cache and "result" in freshness_cache:
        result = freshness_cache["result"]
        if result.get("warn") and result.get("message"):
            return result["message"]
    return None


def tool_check_freshness(admin_conn) -> dict:
    """Check data freshness for all sources. Uses admin conn for raw access."""
    start = time.time()
    result = check_freshness(admin_conn)
    duration_ms = int((time.time() - start) * 1000)

    log_entry({
        "tool": "check_freshness",
        "result": result,
        "duration_ms": duration_ms,
    })
    return result


def tool_revenue_summary(
    admin_conn,
    reader_conn,
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str | None = None,
    freshness_cache: dict | None = None,
) -> dict:
    """Query revenue data from marts.mart_revenue."""
    start = time.time()
    if freshness_cache is None:
        freshness_cache = {}

    refusal = _gate(admin_conn, freshness_cache)
    if refusal:
        log_entry({"tool": "revenue_summary", "refused": True, **refusal})
        return refusal

    conditions = []
    params = []
    if date_from:
        conditions.append("payment_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("payment_date <= %s")
        params.append(date_to)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    if group_by == "service":
        sql = f"""
            SELECT
                service_description,
                sum(transaction_count) AS transaction_count,
                round(sum(revenue_dollars), 2) AS revenue_dollars,
                round(sum(net_revenue_dollars), 2) AS net_revenue_dollars,
                round(avg(avg_ticket_dollars), 2) AS avg_ticket_dollars,
                sum(refund_count) AS refund_count
            FROM marts.mart_revenue
            {where}
            GROUP BY service_description
            ORDER BY revenue_dollars DESC
        """
    elif group_by == "date":
        sql = f"""
            SELECT
                payment_date,
                sum(transaction_count) AS transaction_count,
                round(sum(revenue_dollars), 2) AS revenue_dollars,
                round(sum(net_revenue_dollars), 2) AS net_revenue_dollars,
                sum(refund_count) AS refund_count
            FROM marts.mart_revenue
            {where}
            GROUP BY payment_date
            ORDER BY payment_date
        """
    else:
        sql = f"""
            SELECT
                sum(transaction_count) AS transaction_count,
                round(sum(revenue_dollars), 2) AS revenue_dollars,
                round(sum(net_revenue_dollars), 2) AS net_revenue_dollars,
                round(avg(avg_ticket_dollars), 2) AS avg_ticket_dollars,
                sum(refund_count) AS refund_count,
                round(sum(refund_dollars), 2) AS refund_dollars
            FROM marts.mart_revenue
            {where}
        """

    rows = query(reader_conn, sql, tuple(params) if params else None)
    duration_ms = int((time.time() - start) * 1000)

    result = {"data": rows, "sql": sql.strip(), "row_count": len(rows)}
    caveat = _caveat(freshness_cache)
    if caveat:
        result["caveat"] = caveat

    log_entry({
        "tool": "revenue_summary",
        "parameters": {"date_from": date_from, "date_to": date_to, "group_by": group_by},
        "sql": sql.strip(),
        "row_count": len(rows),
        "duration_ms": duration_ms,
    })
    return result


def tool_call_funnel(
    admin_conn,
    reader_conn,
    date_from: str | None = None,
    date_to: str | None = None,
    freshness_cache: dict | None = None,
) -> dict:
    """Query call funnel data from marts.mart_call_funnel."""
    start = time.time()
    if freshness_cache is None:
        freshness_cache = {}

    refusal = _gate(admin_conn, freshness_cache)
    if refusal:
        log_entry({"tool": "call_funnel", "refused": True, **refusal})
        return refusal

    conditions = []
    params = []
    if date_from:
        conditions.append("call_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("call_date <= %s")
        params.append(date_to)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            sum(total_calls) AS total_calls,
            sum(booked) AS booked,
            sum(qualified) AS qualified,
            sum(escalated) AS escalated,
            sum(missed) AS missed,
            sum(resolved) AS resolved,
            round(100.0 * sum(booked) / nullif(sum(total_calls), 0), 1) AS booking_rate_pct,
            round(100.0 * sum(escalated) / nullif(sum(total_calls), 0), 1) AS escalation_rate_pct,
            round(avg(avg_sentiment), 2) AS avg_sentiment,
            sum(total_jobs) AS total_jobs,
            sum(completed_jobs) AS completed_jobs,
            sum(cancelled_jobs) AS cancelled_jobs
        FROM marts.mart_call_funnel
        {where}
    """

    rows = query(reader_conn, sql, tuple(params) if params else None)
    duration_ms = int((time.time() - start) * 1000)

    result = {"data": rows, "sql": sql.strip(), "row_count": len(rows)}
    caveat = _caveat(freshness_cache)
    if caveat:
        result["caveat"] = caveat

    log_entry({
        "tool": "call_funnel",
        "parameters": {"date_from": date_from, "date_to": date_to},
        "sql": sql.strip(),
        "row_count": len(rows),
        "duration_ms": duration_ms,
    })
    return result


def tool_job_completion(
    admin_conn,
    reader_conn,
    service_category: str | None = None,
    freshness_cache: dict | None = None,
) -> dict:
    """Query job completion data from marts.mart_jobs."""
    start = time.time()
    if freshness_cache is None:
        freshness_cache = {}

    refusal = _gate(admin_conn, freshness_cache)
    if refusal:
        log_entry({"tool": "job_completion", "refused": True, **refusal})
        return refusal

    conditions = []
    params = []
    if service_category:
        conditions.append("service_category = %s")
        params.append(service_category)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            service_category,
            total_jobs,
            completed,
            scheduled,
            cancelled,
            completion_rate_pct,
            avg_completed_value,
            total_completed_value
        FROM marts.mart_jobs
        {where}
        ORDER BY total_completed_value DESC
    """

    rows = query(reader_conn, sql, tuple(params) if params else None)
    duration_ms = int((time.time() - start) * 1000)

    result = {"data": rows, "sql": sql.strip(), "row_count": len(rows)}
    caveat = _caveat(freshness_cache)
    if caveat:
        result["caveat"] = caveat

    log_entry({
        "tool": "job_completion",
        "parameters": {"service_category": service_category},
        "sql": sql.strip(),
        "row_count": len(rows),
        "duration_ms": duration_ms,
    })
    return result


def tool_query_marts(
    admin_conn,
    reader_conn,
    sql: str,
    freshness_cache: dict | None = None,
) -> dict:
    """Execute a validated read-only SQL query against the marts schema."""
    start = time.time()
    if freshness_cache is None:
        freshness_cache = {}

    refusal = _gate(admin_conn, freshness_cache)
    if refusal:
        log_entry({"tool": "query_marts", "refused": True, "input_sql": sql, **refusal})
        return refusal

    ok, error_msg = validate_sql(sql)
    if not ok:
        result = {"error": "query_rejected", "message": error_msg, "input_sql": sql}
        log_entry({
            "tool": "query_marts",
            "rejected": True,
            "input_sql": sql,
            "reason": error_msg,
        })
        return result

    capped_sql = apply_row_cap(sql)

    try:
        cur = reader_conn.cursor()
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.close()

        rows = query(reader_conn, capped_sql)
    except Exception as e:
        reader_conn.rollback()
        result = {"error": "query_failed", "message": str(e), "sql": capped_sql}
        log_entry({
            "tool": "query_marts",
            "error": str(e),
            "sql": capped_sql,
            "duration_ms": int((time.time() - start) * 1000),
        })
        return result

    duration_ms = int((time.time() - start) * 1000)

    result = {"data": rows, "sql": capped_sql, "row_count": len(rows)}
    caveat = _caveat(freshness_cache)
    if caveat:
        result["caveat"] = caveat

    log_entry({
        "tool": "query_marts",
        "input_sql": sql,
        "executed_sql": capped_sql,
        "row_count": len(rows),
        "duration_ms": duration_ms,
    })
    return result


def tool_describe_schema() -> dict:
    """Return schema metadata for all mart tables."""
    log_entry({"tool": "describe_schema"})
    return {"tables": SCHEMA_INFO}
