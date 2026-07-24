"""Load raw JSON from the data lake into the warehouse staging schema."""

import psycopg2
from psycopg2.extras import execute_values

from ingest.config import LakeConfig, WarehouseConfig
from ingest.lake import read_raw

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


def load_to_warehouse(
    lake: LakeConfig, wh: WarehouseConfig, source: str, table: str, columns: list[str]
):
    """Load raw lake data into a warehouse raw table."""
    records = read_raw(lake, source)
    if not records:
        print(f"  No records for {source}, skipping.")
        return 0

    conn = psycopg2.connect(wh.connection_string)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_RAW};")
    cur.execute(_raw_table_ddl(table, columns, wh.type))
    cur.execute(f"TRUNCATE {_RAW}.{table};")

    rows = [tuple(str(r.get(c, "")) for c in columns) for r in records]
    insert_sql = f"INSERT INTO {_RAW}.{table} ({', '.join(columns)}) VALUES %s"
    execute_values(cur, insert_sql, rows)

    print(f"  Loaded {len(rows)} rows into {_RAW}.{table}")
    cur.close()
    conn.close()
    return len(rows)
