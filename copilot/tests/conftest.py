"""Test fixtures for copilot tests."""

import os
import pytest
import psycopg2


def _pg_available():
    """Check if the test Postgres instance is reachable."""
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "reckon"),
            user=os.getenv("POSTGRES_USER", "reckon"),
            password=os.getenv("POSTGRES_PASSWORD", "reckon_dev"),
        )
        conn.close()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _pg_available(),
    reason="Postgres not available (docker compose not running)",
)


@pytest.fixture
def admin_conn():
    """Full-privilege Postgres connection for test setup and freshness checks."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "reckon"),
        user=os.getenv("POSTGRES_USER", "reckon"),
        password=os.getenv("POSTGRES_PASSWORD", "reckon_dev"),
    )
    yield conn
    conn.close()


@pytest.fixture
def reader_conn():
    """Read-only reckon_reader connection restricted to marts schema."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "reckon"),
        user=os.getenv("COPILOT_DB_USER", "reckon_reader"),
        password=os.getenv("COPILOT_DB_PASSWORD", "reckon_reader_dev"),
    )
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    conn.commit()
    cur.close()
    yield conn
    conn.close()


@pytest.fixture
def force_stale(admin_conn):
    """Force all raw tables to have stale _loaded_at timestamps (50 hours ago)."""
    cur = admin_conn.cursor()
    for table in ("raw.aria_calls", "raw.stripe_payments", "raw.jobs"):
        cur.execute(
            f"UPDATE {table} SET _loaded_at = now() - interval '50 hours'"
        )
    admin_conn.commit()
    cur.close()

    yield

    # Restore to fresh timestamps
    cur = admin_conn.cursor()
    for table in ("raw.aria_calls", "raw.stripe_payments", "raw.jobs"):
        cur.execute(f"UPDATE {table} SET _loaded_at = now()")
    admin_conn.commit()
    cur.close()


@pytest.fixture
def force_warn(admin_conn):
    """Force all raw tables to have warn-level _loaded_at (30 hours ago)."""
    cur = admin_conn.cursor()
    for table in ("raw.aria_calls", "raw.stripe_payments", "raw.jobs"):
        cur.execute(
            f"UPDATE {table} SET _loaded_at = now() - interval '30 hours'"
        )
    admin_conn.commit()
    cur.close()

    yield

    cur = admin_conn.cursor()
    for table in ("raw.aria_calls", "raw.stripe_payments", "raw.jobs"):
        cur.execute(f"UPDATE {table} SET _loaded_at = now()")
    admin_conn.commit()
    cur.close()
