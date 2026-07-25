"""Reckon API: serves warehouse data to the dashboard."""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from telemetry import init_telemetry

# The same thresholds the copilot refuses on (copilot/trust_gate.py), dbt's
# source freshness config (transform/models/staging/sources.yml), and the
# Dagster freshness policies on the marts (orchestration/assets_dbt.py). They
# are repeated rather than imported because the API image builds from the api/
# directory alone; api/tests/test_freshness.py fails if they ever drift.
FRESHNESS_WARN_HOURS = 24
FRESHNESS_ERROR_HOURS = 48

# "raw" is a reserved word on Redshift, so the schema is always double-quoted
# (same reason as ingest/loader.py).
FRESHNESS_SOURCES = [
    ("aria_calls", '"raw".aria_calls'),
    ("stripe_payments", '"raw".stripe_payments'),
    ("jobs", '"raw".jobs'),
]


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "warehouse"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "reckon"),
        user=os.getenv("POSTGRES_USER", "reckon"),
        password=os.getenv("POSTGRES_PASSWORD", "reckon_dev"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Reckon API", version="1.0.0", lifespan=lifespan)
init_telemetry(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def query(sql: str) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


@app.get("/health")
def health():
    return {"status": "ok"}


def classify_age(age_hours: float | None) -> str:
    """Bucket a source's age into fresh, warn, or stale.

    Pure, so the thresholds are testable without a warehouse. An unknown age
    (nothing ever loaded) is stale, not fresh: absence of data is not evidence
    of freshness.
    """
    if age_hours is None:
        return "stale"
    if age_hours > FRESHNESS_ERROR_HOURS:
        return "stale"
    if age_hours > FRESHNESS_WARN_HOURS:
        return "warn"
    return "fresh"


@app.get("/api/freshness")
def freshness():
    """How old the warehouse data is, per source.

    The dashboard renders this as a banner so a stale dashboard says it is
    stale instead of quietly presenting old numbers as current. Age is measured
    from ``_loaded_at``, the moment the pipeline landed the row, not from the
    event timestamps, which is the same basis the copilot's trust gate uses.
    """
    now = datetime.now(timezone.utc)
    sources = []

    for name, table in FRESHNESS_SOURCES:
        rows = query(f"SELECT MAX(_loaded_at) AS last_loaded FROM {table}")
        last_loaded = rows[0]["last_loaded"] if rows else None

        if last_loaded is None:
            sources.append({
                "name": name,
                "last_loaded": None,
                "age_hours": None,
                "status": classify_age(None),
            })
            continue

        if last_loaded.tzinfo is None:
            last_loaded = last_loaded.replace(tzinfo=timezone.utc)
        age_hours = (now - last_loaded).total_seconds() / 3600

        sources.append({
            "name": name,
            "last_loaded": last_loaded.isoformat(),
            "age_hours": round(age_hours, 1),
            "status": classify_age(age_hours),
        })

    # The dashboard is only as fresh as its stalest source, so the overall
    # status is the worst one rather than an average.
    order = {"fresh": 0, "warn": 1, "stale": 2}
    overall = max((s["status"] for s in sources), key=lambda s: order[s], default="stale")
    ages = [s["age_hours"] for s in sources if s["age_hours"] is not None]

    return {
        "status": overall,
        "age_hours": max(ages) if ages else None,
        "warn_after_hours": FRESHNESS_WARN_HOURS,
        "stale_after_hours": FRESHNESS_ERROR_HOURS,
        "sources": sources,
    }


@app.get("/api/call-funnel")
def call_funnel():
    return query("SELECT * FROM marts.mart_call_funnel ORDER BY call_date")


@app.get("/api/call-funnel/summary")
def call_funnel_summary():
    return query("""
        SELECT
            sum(total_calls) as total_calls,
            sum(qualified) as total_qualified,
            sum(booked) as total_booked,
            sum(escalated) as total_escalated,
            sum(missed) as total_missed,
            sum(completed_jobs) as total_completed,
            round(100.0 * sum(booked) / nullif(sum(total_calls), 0), 1) as booking_rate_pct,
            round(100.0 * sum(escalated) / nullif(sum(total_calls), 0), 1) as escalation_rate_pct,
            round(avg(avg_sentiment), 2) as avg_sentiment
        FROM marts.mart_call_funnel
    """)


@app.get("/api/revenue")
def revenue():
    return query("""
        SELECT
            payment_date,
            sum(revenue_dollars) as revenue,
            sum(net_revenue_dollars) as net_revenue,
            sum(transaction_count) as transactions
        FROM marts.mart_revenue
        GROUP BY payment_date
        ORDER BY payment_date
    """)


@app.get("/api/jobs/summary")
def jobs_summary():
    return query("""
        SELECT
            sum(total_jobs) as total_jobs,
            sum(completed) as total_completed,
            sum(cancelled) as total_cancelled,
            sum(scheduled) as total_scheduled,
            round(100.0 * sum(completed) / nullif(sum(total_jobs), 0), 1)
                as completion_rate_pct,
            round(sum(total_completed_value), 2) as total_completed_value
        FROM marts.mart_jobs
    """)


@app.get("/api/revenue/by-service")
def revenue_by_service():
    return query("""
        SELECT
            service_description,
            sum(revenue_dollars) as revenue,
            sum(transaction_count) as transactions,
            round(avg(avg_ticket_dollars), 2) as avg_ticket
        FROM marts.mart_revenue
        GROUP BY service_description
        ORDER BY revenue DESC
    """)
