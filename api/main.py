"""Reckon API — serves warehouse data to the dashboard."""

import os
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


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
