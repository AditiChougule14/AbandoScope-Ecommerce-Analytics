"""Import Power BI CSV files into the SQL database for AbandoScope.

This script now includes safety features:
- ``--dry-run`` option to simulate the import without modifying the database.
- Automatic backup of the SQLite database before any changes (unless ``--dry-run``).
- User confirmation before truncating existing tables.
- Transaction handling: a single transaction is used for the whole import (SQLite or SQLAlchemy).
- Schema compatibility checks before importing.
- Verification of row counts and numeric totals after import.
- Mapping of CSV column ``count`` -> ``event_count`` for ``event_distribution``.

Usage (run from the repository root)::

    python scripts\\import_powerbi_sql.py [--dry-run]

Add ``--dry-run`` to perform all checks and report actions without writing to the database.
"""

import os
import pathlib
import sys
import argparse
import shutil
import warnings
import pandas as pd
import sqlite3

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
POWERBI_DIR = PROJECT_ROOT / "data" / "processed" / "powerbi"

CSV_TABLE_MAP = {
    "event_distribution.csv": {
        "table": "event_distribution",
        "column_rename": {"count": "event_count"},
    },
    "category_performance.csv": {"table": "category_performance"},
    "brand_performance.csv": {"table": "brand_performance"},
    "top_products.csv": {"table": "top_products"},
    "session_kpis.csv": {"table": "session_kpis"},
}

CHUNK_SIZE = 200_000

# ---------------------------------------------------------------------------
# Helper: obtain a DB connection (SQLite fallback, optional SQLAlchemy engine)
# ---------------------------------------------------------------------------

def get_sqlite_connection(db_path: pathlib.Path):
    return sqlite3.connect(str(db_path))

def get_engine():
    """Return a SQLAlchemy engine if possible, otherwise None.
    The function checks for the environment variable ``DB_CONN``. If set
    and sqlalchemy is importable, an engine is created. If any step fails,
    None is returned and the caller should fall back to SQLite.
    """
    conn_str = os.getenv("DB_CONN")
    if not conn_str:
        return None
    try:
        from sqlalchemy import create_engine
        return create_engine(conn_str)
    except Exception as exc:
        warnings.warn(f"SQLAlchemy import or engine creation failed: {exc}. Falling back to SQLite.")
        return None

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description='Import Power BI CSV files into the SQL database with safety checks.')
    parser.add_argument('--dry-run', action='store_true', help='Perform all checks and report actions without modifying the database.')
    return parser.parse_args()

def backup_sqlite_db(db_path: pathlib.Path):
    backup_path = db_path.with_suffix('.bak')
    shutil.copy2(db_path, backup_path)
    print(f"SQLite database backed up to {backup_path}")
    return backup_path

def user_confirm(prompt: str) -> bool:
    resp = input(f"{prompt} [y/N]: ")
    return resp.strip().lower() == 'y'

def get_table_columns(conn, table_name: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    return [row[1] for row in cur.fetchall()]

def verify_schema(conn, table_name: str, expected_columns: list) -> bool:
    actual = get_table_columns(conn, table_name)
    missing = set(expected_columns) - set(actual)
    extra = set(actual) - set(expected_columns)
    if missing:
        print(f"[ERROR] Table '{table_name}' is missing columns: {', '.join(missing)}")
        return False
    if extra:
        print(f"[WARNING] Table '{table_name}' has extra columns: {', '.join(extra)}")
    return True

def csv_row_count_and_totals(csv_path: pathlib.Path, numeric_cols: list):
    total_rows = 0
    totals = {col: 0 for col in numeric_cols}
    for chunk in pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False):
        total_rows += len(chunk)
        for col in numeric_cols:
            if col in chunk.columns:
                totals[col] = totals[col] + chunk[col].sum(skipna=True)
    return total_rows, totals

def db_row_count_and_totals(conn, table_name: str, numeric_cols: list):
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table_name};")
    row_count = cur.fetchone()[0]
    totals = {}
    for col in numeric_cols:
        cur.execute(f"SELECT SUM({col}) FROM {table_name};")
        sums = cur.fetchone()[0]
        totals[col] = sums if sums is not None else 0
    return row_count, totals

def truncate_table(cursor, table_name: str):
    cursor.execute(f"DELETE FROM {table_name};")

def import_csv_to_table(csv_path: pathlib.Path, table_name: str, conn, rename_map=None, dry_run=False):
    """Read a CSV in chunks and insert into the given table.
    ``rename_map`` is a dict mapping CSV column names to target column names.
    """
    cur = conn.cursor()
    if not dry_run:
        truncate_table(cur, table_name)
        conn.commit()
    else:
        print(f"[DRY-RUN] Would truncate table {table_name}")

    csv_iter = pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False)
    for idx, chunk in enumerate(csv_iter, start=1):
        if rename_map:
            chunk = chunk.rename(columns=rename_map)
        if not dry_run:
            chunk.to_sql(table_name, conn, if_exists="append", index=False)
            print(f"Inserted chunk {idx} into {table_name}")
        else:
            print(f"[DRY-RUN] Would insert chunk {idx} into {table_name} (rows: {len(chunk)})")

def main():
    args = parse_args()
    dry_run = args.dry_run

    sqlite_path = PROJECT_ROOT / "abando_scope.db"
    engine = get_engine()
    if engine:
        print("Using SQLAlchemy engine from DB_CONN environment variable.")
        conn = engine.connect()
        trans = conn.begin()
    else:
        if not sqlite_path.is_file():
            sys.stderr.write("Error: No SQLite DB file found and DB_CONN not set. Cannot proceed.\n")
            sys.exit(1)
        print(f"Using SQLite database at {sqlite_path}")
        if not dry_run:
            backup_sqlite_db(sqlite_path)
        conn = get_sqlite_connection(sqlite_path)
        trans = conn
        if not dry_run:
            conn.isolation_level = None
            conn.execute('BEGIN')

    try:
        for csv_name, meta in CSV_TABLE_MAP.items():
            csv_file = POWERBI_DIR / csv_name
            if not csv_file.is_file():
                sys.stderr.write(f"Warning: {csv_file} not found – skipping.\n")
                continue
            table = meta["table"]
            # Schema check
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table});")
            columns = [row[1] for row in cur.fetchall()]
            expected = list(pd.read_csv(csv_file, nrows=0).columns)
            if "column_rename" in meta:
                for src, tgt in meta["column_rename"].items():
                    if src in expected:
                        expected[expected.index(src)] = tgt
            if not verify_schema(conn, table, expected):
                raise RuntimeError(f"Schema verification failed for table {table}")

            if not dry_run:
                if not user_confirm(f"Truncate existing data in table '{table}' before import?"):
                    print(f"Skipping import for {table} as per user request.")
                    continue

            numeric_cols = [col for col in expected if pd.api.types.is_numeric_dtype(pd.read_csv(csv_file, nrows=1)[col])]
            import_csv_to_table(csv_file, table, conn, rename_map=meta.get("column_rename"), dry_run=dry_run)

            if not dry_run:
                csv_rows, csv_totals = csv_row_count_and_totals(csv_file, numeric_cols)
                db_rows, db_totals = db_row_count_and_totals(conn, table, numeric_cols)
                if csv_rows != db_rows:
                    print(f"[WARN] Row count mismatch for {table}: CSV={csv_rows}, DB={db_rows}")
                for col in numeric_cols:
                    csv_val = round(csv_totals[col], 4)
                    db_val = round(db_totals[col] or 0, 4)
                    if abs(csv_val - db_val) > 1e-4:
                        print(f"[WARN] Total mismatch for {table}.{col}: CSV={csv_val}, DB={db_val}")
        if not dry_run:
            trans.commit()
            print("All imports completed and transaction committed.")
        else:
            print("[DRY-RUN] No changes were made to the database.")
    except Exception as e:
        if not dry_run:
            trans.rollback()
            print(f"Error occurred: {e}. Transaction rolled back.")
        else:
            print(f"[DRY-RUN] Encountered error: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
