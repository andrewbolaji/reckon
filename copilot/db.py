"""Read-only database connection for the MCP copilot."""

import os

import psycopg2
import psycopg2.extras


def get_conn(*, read_only: bool = True):
    """Return a psycopg2 connection using the copilot reader role.

    When read_only is True (default), the connection uses the reckon_reader
    role which only has SELECT on the marts schema, and the session is set
    to read-only mode as a belt-and-suspenders guard.
    """
    if read_only:
        user = os.getenv("COPILOT_DB_USER", "reckon_reader")
        password = os.getenv("COPILOT_DB_PASSWORD", "reckon_reader_dev")
    else:
        user = os.getenv("POSTGRES_USER", "reckon")
        password = os.getenv("POSTGRES_PASSWORD", "reckon_dev")

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "reckon"),
        user=user,
        password=password,
    )

    if read_only:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
        )
        conn.commit()
        cur.close()

    return conn


def query(conn, sql: str, params: tuple | None = None) -> list[dict]:
    """Execute a parameterized query and return rows as dicts."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows
