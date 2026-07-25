"""Load raw JSON from the data lake into the warehouse staging schema."""

import psycopg2
from psycopg2.extras import execute_values

from ingest.config import LakeConfig, WarehouseConfig
from ingest.lake import read_raw
from ingest.window import DateWindow

# Dialect differences between Postgres (local dev warehouse) and Amazon
# Redshift (prod). Redshift has no TEXT type — it silently maps TEXT to
# VARCHAR(256), risking truncation — and rejects now() as a column default.
# Use VARCHAR(max) and GETDATE() there instead.
_DIALECT = {
    "redshift": {"col_type": "VARCHAR(65535)", "now": "GETDATE()"},
    "postgres": {"col_type": "TEXT", "now": "now()"},
}

# "raw" is a reserved word in Amazon Redshift (a column-encoding keyword), so
# the schema identifier must be double-quoted; unquoted `raw.<table>` is a
# syntax error. Quoting is harmless on Postgres too. dbt quotes this same schema
# via the source's quoting config (transform/models/staging/sources.yml).
_RAW = '"raw"'


def _raw_table_ddl(table: str, columns: list[str], wh_type: str) -> str:
    """Build the CREATE TABLE statement for a raw staging table.

    Pure (no DB connection) so the Postgres/Redshift dialect handling is
    unit-testable. Unknown warehouse types fall back to Postgres.
    """
    d = _DIALECT.get(wh_type, _DIALECT["postgres"])
    col_defs = ", ".join(f"{c} {d['col_type']}" for c in columns)
    col_defs += f", _loaded_at TIMESTAMP DEFAULT {d['now']}"
    return f"CREATE TABLE IF NOT EXISTS {_RAW}.{table} ({col_defs});"


def _partition_delete_sql(table: str, date_column: str) -> str:
    """Build the DELETE that clears one date window from a raw table.

    Pure, for the same reason as ``_raw_table_ddl``: the dialect trickiness is
    worth testing without a warehouse.

    Every raw column is stored as text and every source timestamp is ISO-8601,
    so the first 10 characters are the calendar date. Comparing that prefix
    beats casting: Redshift and Postgres disagree about casting malformed text
    to a date, and a single unparseable row would fail the whole delete.

    The date column is double-quoted because ``timestamp`` is both a column name
    here and a type name in both engines.
    """
    return (
        f'DELETE FROM {_RAW}.{table} '
        f'WHERE substring("{date_column}", 1, 10) BETWEEN %s AND %s;'
    )


def load_to_warehouse(
    lake: LakeConfig,
    wh: WarehouseConfig,
    source: str,
    table: str,
    columns: list[str],
    window: DateWindow | None = None,
    date_column: str | None = None,
):
    """Load raw lake data into a warehouse raw table.

    With no window this is a full refresh: truncate, then reload everything.
    With a window only that date range is deleted and reinserted, so a backfill
    of one week leaves every other week standing. An empty window still deletes,
    because a refill that finds a source empty for those days must leave them
    empty rather than leave stale rows behind.
    """
    if window is not None and not date_column:
        raise ValueError("date_column is required when loading a window")

    records = read_raw(lake, source, window=window)
    if not records and window is None:
        print(f"  No records for {source}, skipping.")
        return 0

    conn = psycopg2.connect(wh.connection_string)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_RAW};")
    cur.execute(_raw_table_ddl(table, columns, wh.type))

    if window is None:
        cur.execute(f"TRUNCATE {_RAW}.{table};")
    else:
        cur.execute(
            _partition_delete_sql(table, date_column),
            (window.start_iso, window.end_iso),
        )

    rows = [tuple(str(r.get(c, "")) for c in columns) for r in records]
    if rows:
        insert_sql = f"INSERT INTO {_RAW}.{table} ({', '.join(columns)}) VALUES %s"
        execute_values(cur, insert_sql, rows)

    scope = f" for {window}" if window else ""
    print(f"  Loaded {len(rows)} rows into {_RAW}.{table}{scope}")
    cur.close()
    conn.close()
    return len(rows)
