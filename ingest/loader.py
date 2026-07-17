"""Load raw JSON from the data lake into the warehouse staging schema."""

import json
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

from ingest.config import LakeConfig, WarehouseConfig


def _load_local_files(lake: LakeConfig, source: str) -> list[dict]:
    """Read all JSON files for a source from the local lake."""
    source_dir = Path(lake.path) / "raw" / source
    records = []
    for f in sorted(source_dir.rglob("*.json")):
        records.extend(json.loads(f.read_text()))
    return records


def load_to_warehouse(
    lake: LakeConfig, wh: WarehouseConfig, source: str, table: str, columns: list[str]
):
    """Load raw lake data into a warehouse raw table."""
    records = _load_local_files(lake, source)
    if not records:
        print(f"  No records for {source}, skipping.")
        return 0

    conn = psycopg2.connect(wh.connection_string)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"CREATE SCHEMA IF NOT EXISTS raw;")

    col_defs = ", ".join(f"{c} TEXT" for c in columns)
    col_defs += ", _loaded_at TIMESTAMP DEFAULT now()"
    cur.execute(f"CREATE TABLE IF NOT EXISTS raw.{table} ({col_defs});")
    cur.execute(f"TRUNCATE raw.{table};")

    rows = [tuple(str(r.get(c, "")) for c in columns) for r in records]
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO raw.{table} ({', '.join(columns)}) VALUES %s"
    execute_values(cur, insert_sql, rows)

    print(f"  Loaded {len(rows)} rows into raw.{table}")
    cur.close()
    conn.close()
    return len(rows)
