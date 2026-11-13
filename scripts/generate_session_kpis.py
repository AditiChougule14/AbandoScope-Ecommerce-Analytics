"""Generate session‑level KPIs for the AbandoScope project.

This script works on the cleaned CSV (data/processed/clean_2019_oct.csv)
using chunked pandas reading and a temporary SQLite database to aggregate
per‑session flags without loading the whole ~5.8 GB file into RAM.

KPIs computed:
  • total_sessions – number of distinct user sessions
  • sessions_with_view – sessions that contain at least one "view" event
  • sessions_with_cart – sessions that contain at least one "cart" event
  • sessions_with_purchase – sessions that contain at least one "purchase" event
  • abandoned_sessions – sessions with cart activity but **no** purchase
  • cart_abandonment_rate – abandoned_sessions / sessions_with_cart
  • abandoned_cart_value – sum of cart‑value (price) for abandoned sessions

Limitations:
  – The script only uses the columns required for the above metrics.
  – If the cleaned CSV contains malformed rows they will be skipped by pandas.
  – Cart value is the *estimated* value of items added to the cart (price
    column) and does **not** represent actual lost revenue.

The results are written to data/processed/powerbi/session_kpis.csv and also
printed to stdout.
"""

import pathlib
import shutil
import sqlite3
import sys
import csv
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RAW_CLEANED_CSV = pathlib.Path(r"D:\AbandoScope_Analytics\data\processed\clean_2019_oct.csv")
POWERBI_DIR = pathlib.Path(r"D:\AbandoScope_Analytics\data\processed\powerbi")
OUTPUT_CSV = POWERBI_DIR / "session_kpis.csv"
CHUNK_SIZE = 200_000

# Temporary SQLite file (stored alongside the script; will be removed at the end)
TEMP_DB_PATH = pathlib.Path("session_kpis_tmp.db")

def init_db(conn: sqlite3.Connection) -> None:
    """Create the sessions table used for aggregation.

    Columns:
        user_session   TEXT PRIMARY KEY
        has_view       INTEGER (0/1)
        has_cart       INTEGER (0/1)
        has_purchase   INTEGER (0/1)
        cart_value     REAL – sum of price for cart events in the session
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            user_session TEXT PRIMARY KEY,
            has_view INTEGER NOT NULL DEFAULT 0,
            has_cart INTEGER NOT NULL DEFAULT 0,
            has_purchase INTEGER NOT NULL DEFAULT 0,
            cart_value REAL NOT NULL DEFAULT 0.0
        )
        """
    )
    conn.commit()


def upsert_sessions(conn: sqlite3.Connection, rows) -> None:
    """Insert or update session aggregates for a batch of rows.

    ``rows`` is an iterable of tuples matching the table schema.
    The UPSERT logic keeps a flag as 1 if any chunk reported it and sums
    cart values across chunks.
    """
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO sessions (user_session, has_view, has_cart, has_purchase, cart_value)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_session) DO UPDATE SET
            has_view = MAX(sessions.has_view, excluded.has_view),
            has_cart = MAX(sessions.has_cart, excluded.has_cart),
            has_purchase = MAX(sessions.has_purchase, excluded.has_purchase),
            cart_value = sessions.cart_value + excluded.cart_value
        """,
        rows,
    )
    conn.commit()


def main():
    if not RAW_CLEANED_CSV.is_file():
        sys.stderr.write(f"Error: cleaned CSV not found at {RAW_CLEANED_CSV}\n")
        sys.exit(1)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure any stale temp DB is removed
    if TEMP_DB_PATH.exists():
        TEMP_DB_PATH.unlink()
    conn = sqlite3.connect(str(TEMP_DB_PATH))
    init_db(conn)

    csv_iter = pd.read_csv(
        RAW_CLEANED_CSV,
        chunksize=CHUNK_SIZE,
        dtype={
            "event_type": "category",
            "user_session": "object",
            "price": "float64",
        },
        low_memory=False,
    )

    for chunk_idx, chunk in enumerate(csv_iter, start=1):
        # Basic per‑session flags within this chunk
        sess_grp = chunk.groupby("user_session")
        upsert_rows = []
        for sess_id, grp in sess_grp:
            has_view = int((grp["event_type"] == "view").any())
            has_cart = int((grp["event_type"] == "cart").any())
            has_purchase = int((grp["event_type"] == "purchase").any())
            cart_val = float(grp[grp["event_type"] == "cart"]["price"].sum())
            upsert_rows.append((sess_id, has_view, has_cart, has_purchase, cart_val))
        upsert_sessions(conn, upsert_rows)
        print(f"Processed chunk {chunk_idx}")

    # ---------------------------------------------------------------------
    # Compute final KPIs from the SQLite DB
    # ---------------------------------------------------------------------
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cur.fetchone()[0]
    cur.execute("SELECT SUM(has_view) FROM sessions")
    sessions_with_view = cur.fetchone()[0] or 0
    cur.execute("SELECT SUM(has_cart) FROM sessions")
    sessions_with_cart = cur.fetchone()[0] or 0
    cur.execute("SELECT SUM(has_purchase) FROM sessions")
    sessions_with_purchase = cur.fetchone()[0] or 0
    cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE has_cart = 1 AND has_purchase = 0"
    )
    abandoned_sessions = cur.fetchone()[0]
    cur.execute(
        "SELECT SUM(cart_value) FROM sessions WHERE has_cart = 1 AND has_purchase = 0"
    )
    abandoned_cart_value = cur.fetchone()[0] or 0.0
    cart_abandonment_rate = (
        abandoned_sessions / sessions_with_cart if sessions_with_cart else 0.0
    )

    # ---------------------------------------------------------------------
    # Write results to CSV (atomic write)
    # ---------------------------------------------------------------------
    temp_path = OUTPUT_CSV.with_suffix('.tmp')
    with temp_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['metric', 'value'])
        writer.writerow(['total_sessions', total_sessions])
        writer.writerow(['sessions_with_view', sessions_with_view])
        writer.writerow(['sessions_with_cart', sessions_with_cart])
        writer.writerow(['sessions_with_purchase', sessions_with_purchase])
        writer.writerow(['abandoned_sessions', abandoned_sessions])
        writer.writerow(['cart_abandonment_rate', f"{cart_abandonment_rate:.6f}"])
        writer.writerow(['abandoned_cart_value', f"{abandoned_cart_value:.2f}"])
    shutil.move(str(temp_path), str(OUTPUT_CSV))

    # ---------------------------------------------------------------------
    # Print metrics
    # ---------------------------------------------------------------------
    print("\n--- Session KPIs ---")
    print(f"Total sessions:               {total_sessions}")
    print(f"Sessions with view events:    {sessions_with_view}")
    print(f"Sessions with cart events:    {sessions_with_cart}")
    print(f"Sessions with purchase events:{sessions_with_purchase}")
    print(f"Abandoned sessions:           {abandoned_sessions}")
    print(f"Cart abandonment rate:        {cart_abandonment_rate:.4%}")
    print(f"Potential abandoned cart value:${abandoned_cart_value:,.2f}")

    conn.close()
    # Clean up temporary DB file
    if TEMP_DB_PATH.exists():
        TEMP_DB_PATH.unlink()

if __name__ == "__main__":
    main()
