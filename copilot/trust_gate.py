"""Trust gate: freshness checking and SQL validation."""

import re
from datetime import datetime, timezone

from copilot.db import query

FRESHNESS_WARN_HOURS = 24
FRESHNESS_ERROR_HOURS = 48

ALLOWED_TABLES = {
    "marts.mart_call_funnel",
    "marts.mart_revenue",
    "marts.mart_jobs",
    "mart_call_funnel",
    "mart_revenue",
    "mart_jobs",
}

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|"
    r"GRANT|REVOKE|COPY|EXECUTE|CALL|DO|SET|RESET|"
    r"LOCK|VACUUM|ANALYZE|CLUSTER|REINDEX|REFRESH|"
    r"BEGIN|COMMIT|ROLLBACK|SAVEPOINT|PREPARE|DEALLOCATE|"
    r"LISTEN|NOTIFY|LOAD|IMPORT|EXPORT"
    r")\b",
    re.IGNORECASE,
)

RAW_STAGING_PATTERN = re.compile(
    r"\b(raw|staging|pg_catalog|information_schema)\s*\.",
    re.IGNORECASE,
)

SOURCES = [
    ("aria_calls", "raw.aria_calls"),
    ("stripe_payments", "raw.stripe_payments"),
    ("jobs", "raw.jobs"),
]


def check_freshness(conn) -> dict:
    """Check data freshness using _loaded_at from raw tables.

    Returns a dict with:
      - fresh: True if all sources are below the error threshold
      - warn: True if any source is between warn and error thresholds
      - sources: list of per-source status dicts
      - message: human-readable summary (only if warn or error)
    """
    now = datetime.now(timezone.utc)
    sources = []
    any_error = False
    any_warn = False
    messages = []

    for name, table in SOURCES:
        rows = query(
            conn,
            f"SELECT MAX(_loaded_at) AS last_loaded FROM {table}",
        )
        last_loaded = rows[0]["last_loaded"] if rows and rows[0]["last_loaded"] else None

        if last_loaded is None:
            sources.append({
                "name": name,
                "last_loaded": None,
                "age_hours": None,
                "status": "error",
            })
            any_error = True
            messages.append(f"{name}: no data loaded")
            continue

        if last_loaded.tzinfo is None:
            last_loaded = last_loaded.replace(tzinfo=timezone.utc)

        age_hours = (now - last_loaded).total_seconds() / 3600
        if age_hours > FRESHNESS_ERROR_HOURS:
            status = "error"
            any_error = True
            messages.append(
                f"{name}: stale ({age_hours:.0f}h old, threshold is {FRESHNESS_ERROR_HOURS}h)"
            )
        elif age_hours > FRESHNESS_WARN_HOURS:
            status = "warn"
            any_warn = True
            messages.append(
                f"{name}: data is {age_hours:.0f}h old (warn threshold is {FRESHNESS_WARN_HOURS}h)"
            )
        else:
            status = "fresh"

        sources.append({
            "name": name,
            "last_loaded": last_loaded.isoformat(),
            "age_hours": round(age_hours, 1),
            "status": status,
        })

    result = {
        "fresh": not any_error,
        "warn": any_warn,
        "sources": sources,
    }

    if any_error:
        result["message"] = (
            "Cannot answer: data is stale. "
            + "; ".join(messages)
            + ". Please run the pipeline before querying."
        )
    elif any_warn:
        result["message"] = (
            "Note: " + "; ".join(messages)
            + ". Answers reflect data as of those times."
        )

    return result


def validate_sql(sql: str) -> tuple[bool, str]:
    """Validate a SQL string for the query_marts tool.

    Returns (ok, error_message). If ok is True, the SQL is safe to execute.
    """
    stripped = sql.strip()

    if not stripped:
        return False, "Empty query"

    # Strip leading comments
    no_comments = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL)
    no_comments = re.sub(r"--[^\n]*", " ", no_comments)
    no_comments = no_comments.strip()

    if not no_comments.upper().startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    if ";" in stripped:
        return False, "Multi-statement queries are not allowed"

    forbidden = _FORBIDDEN_KEYWORDS.search(no_comments)
    if forbidden:
        keyword = forbidden.group(1).upper()
        # SELECT is allowed, skip it
        if keyword != "SELECT":
            return False, f"Forbidden keyword: {keyword}"

    # Re-check: the regex above catches INSERT etc. but SELECT is in the
    # string. We need to scan only *after* the leading SELECT keyword.
    body = re.sub(r"^SELECT\b", "", no_comments, count=1, flags=re.IGNORECASE)
    forbidden_in_body = _FORBIDDEN_KEYWORDS.search(body)
    if forbidden_in_body:
        keyword = forbidden_in_body.group(1).upper()
        return False, f"Forbidden keyword: {keyword}"

    if RAW_STAGING_PATTERN.search(stripped):
        return False, "Access to raw, staging, pg_catalog, and information_schema is not allowed"

    # Check all table references are in the allowlist
    table_refs = re.findall(
        r"\b(?:FROM|JOIN)\s+([\w]+\.[\w]+|[\w]+)",
        no_comments,
        re.IGNORECASE,
    )
    for ref in table_refs:
        if ref.lower() not in ALLOWED_TABLES:
            return False, f"Table not allowed: {ref}. Only marts tables are accessible."

    return True, ""


def apply_row_cap(sql: str, max_rows: int = 100) -> str:
    """Ensure the query has a LIMIT and it does not exceed max_rows."""
    limit_match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    if limit_match:
        requested = int(limit_match.group(1))
        if requested > max_rows:
            sql = sql[:limit_match.start(1)] + str(max_rows) + sql[limit_match.end(1):]
        return sql
    return sql.rstrip().rstrip(";") + f" LIMIT {max_rows}"
