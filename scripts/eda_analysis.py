# -*- coding: utf-8 -*-
"""scripts/eda_analysis.py

Memory‑efficient Exploratory Data Analysis for the cleaned AbandoScope dataset.

The script processes ``data/processed/clean_2019_oct.csv`` in chunks, avoiding
loading the 5.85 GB file into RAM.  Results are written to:

* ``reports/eda/`` – PNG charts
* ``data/processed/powerbi/`` – CSV files ready for import into Power BI
* ``reports/EDA_Report.md`` – Markdown report with methodology, key findings
  and business recommendations.

Key implementation points following the latest user request:

* No ``psutil`` dependency – disk‑space checks use the standard ``shutil``.
* Session‑level aggregation now uses a **disk‑based SQLite database** stored in a
  temporary project folder.  UPSERTs are performed in batched ``executemany``
  calls, avoiding per‑row SELECT/UPDATE/INSERT cycles.
* All temporary files (including the SQLite database) are removed on both
  successful completion and on any failure.
* ``--dry-run`` now processes only the first 100 000 rows, giving a quick sanity
  check without scanning the full 42‑million‑row file.
* Event‑level conversion rates (view→cart→purchase) are reported **separately**
  from session‑level conversion rates (sessions with cart / purchase).
* The potential abandoned‑cart value is explicitly documented as possibly
  inflated by repeated cart events; it is **not** presented as actual lost
  revenue.
* Final output files are checked beforehand; the script aborts if any would be
  overwritten.
* The raw and cleaned CSV files remain untouched.
"""

import argparse
import csv
import datetime
import os
import pathlib
import shutil
import sqlite3
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration constants (user‑specified expectations)
# ---------------------------------------------------------------------------
DATA_DIR = pathlib.Path("D:/AbandoScope_Analytics/data/processed")
RAW_CLEANED_CSV = DATA_DIR / "clean_2019_oct.csv"
POWERBI_DIR = DATA_DIR / "powerbi"
REPORTS_DIR = pathlib.Path("D:/AbandoScope_Analytics/reports/eda")
CHUNK_SIZE = 1_000_000  # rows per pandas chunk (used for full run)
DRY_RUN_MAX_ROWS = 100_000  # rows processed when --dry-run is used
EXPECTED_TOTAL_ROWS = 42_448_764
EXPECTED_EVENT_COUNTS = {
    "view": 40_779_399,
    "cart": 926_516,
    "purchase": 742_849,
}
EXPECTED_MIN_TIME = "2019-10-01 00:00:00"
EXPECTED_MAX_TIME = "2019-10-31 23:59:59"
# Temporary SQLite database path (disk‑based)
TEMP_DB_DIR = pathlib.Path("D:/AbandoScope_Analytics/tmp")
TEMP_DB_PATH = TEMP_DB_DIR / "session_metrics.db"
# ---------------------------------------------------------------------------

def _ensure_output_dirs() -> None:
    """Create output directories if they do not exist."""
    for d in (POWERBI_DIR, REPORTS_DIR, TEMP_DB_DIR):
        d.mkdir(parents=True, exist_ok=True)

def _check_existing_output() -> None:
    """Abort if any final output file already exists.

    This protects against silent overwrites; the user must delete or rename the
    files before re‑running.
    """
    outputs = [
        POWERBI_DIR / "event_distribution.csv",
        POWERBI_DIR / "category_performance.csv",
        POWERBI_DIR / "brand_performance.csv",
        POWERBI_DIR / "top_products.csv",
        REPORTS_DIR / "EDA_Report.md",
        REPORTS_DIR / "event_distribution.png",
        REPORTS_DIR / "conversion_funnel.png",
        REPORTS_DIR / "cart_abandonment.png",
    ]
    existing = [str(p) for p in outputs if p.exists()]
    if existing:
        raise FileExistsError(
            "The following output files already exist and would be overwritten:\n"
            + "\n".join(existing)
        )

def _parse_timestamp(ts: str) -> datetime.datetime:
    """Parse ``event_time`` strings like ``YYYY-MM-DD HH:MM:SS UTC``."""
    ts = ts.rstrip(" UTC")
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

def _check_free_space() -> None:
    """Require at least 1.2× source‑file size free before opening outputs.

    Mirrors the safety check from the cleaning script.
    """
    src_size = RAW_CLEANED_CSV.stat().st_size
    required = src_size * 1.2
    free = shutil.disk_usage(RAW_CLEANED_CSV.parent).free
    if free < required:
        raise RuntimeError(
            f"Insufficient free disk space. Required >= {required / (1024**3):.2f} GB, "
            f"available {free / (1024**3):.2f} GB."
        )

def _init_session_db(conn: sqlite3.Connection) -> None:
    """Create the ``sessions`` table for disk‑based aggregation.

    Columns:
        session_id   TEXT PRIMARY KEY
        has_view     INTEGER NOT NULL (0/1)
        has_cart     INTEGER NOT NULL
        has_purchase INTEGER NOT NULL
        cart_value   REAL NOT NULL
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            has_view INTEGER NOT NULL,
            has_cart INTEGER NOT NULL,
            has_purchase INTEGER NOT NULL,
            cart_value REAL NOT NULL
        )
        """
    )
    conn.commit()

def _upsert_sessions(conn: sqlite3.Connection, rows: List[Tuple]):
    """Batch UPSERT of session aggregates.

    ``rows`` is a list of tuples:
        (session_id, has_view, has_cart, has_purchase, cart_value)
    """
    sql = """
        INSERT INTO sessions (session_id, has_view, has_cart, has_purchase, cart_value)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            has_view = MAX(has_view, excluded.has_view),
            has_cart = MAX(has_cart, excluded.has_cart),
            has_purchase = MAX(has_purchase, excluded.has_purchase),
            cart_value = cart_value + excluded.cart_value
    """
    conn.executemany(sql, rows)
    conn.commit()

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Memory‑efficient EDA for AbandoScope cleaned data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process a small sample (100k rows) and stop before writing output files.",
    )
    args = parser.parse_args(argv)

    if not RAW_CLEANED_CSV.is_file():
        print(f"Cleaned CSV not found at {RAW_CLEANED_CSV}", file=sys.stderr)
        return 1

    _ensure_output_dirs()
    try:
        _check_existing_output()
        _check_free_space()
    except (FileExistsError, RuntimeError) as e:
        print(e, file=sys.stderr)
        return 1

    # -------------------------------------------------------------------
    # Aggregation containers
    # -------------------------------------------------------------------
    event_counts: Dict[str, int] = defaultdict(int)
    total_revenue: float = 0.0
    min_timestamp: datetime.datetime | None = None
    max_timestamp: datetime.datetime | None = None

    category_agg = None  # DataFrame placeholder
    brand_agg = None
    product_agg = None
    category_rev = defaultdict(float)
    brand_rev_dict = defaultdict(float)
    product_rev_dict = defaultdict(float)

    # -------------------------------------------------------------------
    # Disk‑based SQLite for session‑level metrics
    # -------------------------------------------------------------------
    # Ensure any stale temp DB is removed first
    if TEMP_DB_PATH.exists():
        TEMP_DB_PATH.unlink()
    conn = sqlite3.connect(str(TEMP_DB_PATH))
    try:
        _init_session_db(conn)

        # -------------------------------------------------------------------
        # Streaming CSV processing
        # -------------------------------------------------------------------
        csv_iter = pd.read_csv(
            RAW_CLEANED_CSV,
            chunksize=CHUNK_SIZE,
            dtype={
                "event_time": "object",
                "event_type": "category",
                "product_id": "int64",
                "category_id": "int64",
                "category_code": "object",
                "brand": "object",
                "price": "float64",
                "user_id": "int64",
                "user_session": "object",
            },
            low_memory=False,
        )

        total_rows_processed = 0
        for chunk_idx, chunk in enumerate(csv_iter, start=1):
            # Stop early if dry‑run limit already reached
            if args.dry_run and total_rows_processed >= DRY_RUN_MAX_ROWS:
                break

            # Determine number of rows in this chunk
            rows = len(chunk)

            # Trim for dry‑run if this chunk would exceed the limit
            if args.dry_run and total_rows_processed + rows > DRY_RUN_MAX_ROWS:
                needed = DRY_RUN_MAX_ROWS - total_rows_processed
                if needed <= 0:
                    break
                chunk = chunk.iloc[:needed]
                rows = needed

            total_rows_processed += rows
            print(f"Processing chunk {chunk_idx}: {rows:,} rows (total {total_rows_processed:,})")

            # Basic event counts
            for ev, cnt in chunk["event_type"].value_counts().items():
                event_counts[ev] += int(cnt)

            # Revenue from purchases only
            purchase_mask = chunk["event_type"] == "purchase"
            total_revenue += float(chunk.loc[purchase_mask, "price"].sum())

            # Timestamp bounds
            times = pd.to_datetime(
                chunk["event_time"].str.rstrip(" UTC"),
                format="%Y-%m-%d %H:%M:%S",
                errors="coerce",
            )
            chunk_min = times.min()
            chunk_max = times.max()
            if pd.notnull(chunk_min):
                if min_timestamp is None or chunk_min < min_timestamp:
                    min_timestamp = chunk_min
            if pd.notnull(chunk_max):
                if max_timestamp is None or chunk_max > max_timestamp:
                    max_timestamp = chunk_max

            # Category aggregation (event counts & revenue)
            cat_grp = chunk.groupby(["category_code", "event_type"])
            cat_counts = cat_grp.size().unstack(fill_value=0)
            cat_rev = (
                chunk[chunk["event_type"] == "purchase"].groupby("category_code")["price"].sum()
            )
            if category_agg is None:
                category_agg = cat_counts.copy()
            else:
                category_agg = category_agg.add(cat_counts, fill_value=0)
            for cat, rev in cat_rev.items():
                category_rev[cat] += float(rev)

            # Brand aggregation
            # Normalize brand values: strip whitespace, treat empty/NaN as NO_BRAND
            chunk["brand"] = (
                chunk["brand"]
                .astype(str)
                .str.strip()
                .replace("", "NO_BRAND")
                .replace("nan", "NO_BRAND")
            )
            brand_grp = chunk.groupby(["brand", "event_type"])
            brand_counts = brand_grp.size().unstack(fill_value=0)
            brand_rev = (
                chunk[chunk["event_type"] == "purchase"].groupby("brand")["price"].sum()
            )
            if brand_agg is None:
                brand_agg = brand_counts.copy()
            else:
                brand_agg = brand_agg.add(brand_counts, fill_value=0)
            for br, rev in brand_rev.items():
                brand_rev_dict[br] += float(rev)

            # Product aggregation
            prod_grp = chunk.groupby(["product_id", "event_type"]).size().unstack(fill_value=0)
            prod_rev = (
                chunk[chunk["event_type"] == "purchase"].groupby("product_id")["price"].sum()
            )
            if product_agg is None:
                product_agg = prod_grp.copy()
            else:
                product_agg = product_agg.add(prod_grp, fill_value=0)
            for pid, rev in prod_rev.items():
                product_rev_dict[pid] += float(rev)

            # Session‑level metrics using SQLite upserts
            sess_grp = chunk.groupby("user_session")
            upsert_rows: List[Tuple] = []
            for sess_id, grp in sess_grp:
                has_view = int((grp["event_type"] == "view").any())
                has_cart = int((grp["event_type"] == "cart").any())
                has_purchase = int((grp["event_type"] == "purchase").any())
                cart_val = float(grp.loc[grp["event_type"] == "cart", "price"].sum())
                upsert_rows.append((sess_id, has_view, has_cart, has_purchase, cart_val))
            _upsert_sessions(conn, upsert_rows)

            # Dry‑run early exit after processing this chunk

        # -------------------------------------------------------------------
        # Sanity checks (skip for dry‑run)
        # -------------------------------------------------------------------
        print("Finished streaming pass. Performing sanity checks...")
        if not args.dry_run:
            if total_rows_processed != EXPECTED_TOTAL_ROWS:
                print(
                    f"Row count mismatch: expected {EXPECTED_TOTAL_ROWS:,} but processed {total_rows_processed:,}",
                    file=sys.stderr,
                )
                return 1
            for ev, expected in EXPECTED_EVENT_COUNTS.items():
                actual = event_counts.get(ev, 0)
                if actual != expected:
                    print(
                        f"Event count mismatch for '{ev}': expected {expected:,} got {actual:,}",
                        file=sys.stderr,
                    )
                    return 1
            if min_timestamp is None or max_timestamp is None:
                print("Failed to compute timestamp bounds.", file=sys.stderr)
                return 1
            if min_timestamp != _parse_timestamp(EXPECTED_MIN_TIME):
                print(
                    f"Min timestamp mismatch: expected {EXPECTED_MIN_TIME} got {min_timestamp}",
                    file=sys.stderr,
                )
                return 1
            if max_timestamp != _parse_timestamp(EXPECTED_MAX_TIME):
                print(
                    f"Max timestamp mismatch: expected {EXPECTED_MAX_TIME} got {max_timestamp}",
                    file=sys.stderr,
                )
                return 1

        # -------------------------------------------------------------------
        # Session‑level conversion and abandonment metrics
        # -------------------------------------------------------------------
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sessions WHERE has_view = 1")
        sessions_with_view = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sessions WHERE has_cart = 1")
        sessions_with_cart = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sessions WHERE has_purchase = 1")
        sessions_with_purchase = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM sessions WHERE has_cart = 1 AND has_purchase = 0"
        )
        abandoned_sessions = cur.fetchone()[0]
        cur.execute(
            "SELECT SUM(cart_value) FROM sessions WHERE has_cart = 1 AND has_purchase = 0"
        )
        abandoned_value = cur.fetchone()[0] or 0.0

        # Conversion rates
        event_funnel_rates = {
            "view_to_cart": (
                event_counts.get("cart", 0) / event_counts.get("view", 1)
            ),
            "cart_to_purchase": (
                event_counts.get("purchase", 0) / event_counts.get("cart", 1)
            ),
        }
        session_funnel_rates = {
            "view_to_cart": (
                sessions_with_cart / sessions_with_view if sessions_with_view else 0.0
            ),
            "cart_to_purchase": (
                sessions_with_purchase / sessions_with_cart if sessions_with_cart else 0.0
            ),
        }
        abandonment_rate = (
            abandoned_sessions / sessions_with_cart if sessions_with_cart else 0.0
        )

        if args.dry_run:
            print("Dry‑run complete. No output files were written.")
            return 0

        # -------------------------------------------------------------------
        # Helper for atomic CSV write
        # -------------------------------------------------------------------
        def _write_csv(final_path: pathlib.Path, header: List[str], rows: List[Tuple]):
            temp_path = final_path.with_suffix('.tmp')
            with temp_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            os.replace(temp_path, final_path)

        # -------------------------------------------------------------------
        # Generate Power BI CSVs
        # -------------------------------------------------------------------
        _write_csv(
            POWERBI_DIR / "event_distribution.csv",
            ["event_type", "count"],
            sorted(event_counts.items()),
        )

        cat_rows = []
        for cat, cnts in category_agg.iterrows():
            cat_rows.append(
                (
                    cat,
                    int(cnts.get("view", 0)),
                    int(cnts.get("cart", 0)),
                    int(cnts.get("purchase", 0)),
                    f"{category_rev.get(cat, 0.0):.2f}",
                )
            )
        _write_csv(
            POWERBI_DIR / "category_performance.csv",
            ["category_code", "views", "carts", "purchases", "revenue"],
            sorted(cat_rows, key=lambda x: x[0]),
        )

        brand_rows = []
        for br, cnts in brand_agg.iterrows():
            brand_rows.append(
                (
                    br,
                    int(cnts.get("view", 0)),
                    int(cnts.get("cart", 0)),
                    int(cnts.get("purchase", 0)),
                    f"{brand_rev_dict.get(br, 0.0):.2f}",
                )
            )
        _write_csv(
            POWERBI_DIR / "brand_performance.csv",
            ["brand", "views", "carts", "purchases", "revenue"],
            sorted(brand_rows, key=lambda x: x[0]),
        )

        top_n = 20
        top_product_ids = sorted(
            product_rev_dict.keys(), key=lambda pid: product_rev_dict[pid], reverse=True
        )[:top_n]
        top_rows = []
        for pid in top_product_ids:
            cnts = product_agg.loc[pid] if pid in product_agg.index else {}
            top_rows.append(
                (
                    pid,
                    int(cnts.get("view", 0)),
                    int(cnts.get("cart", 0)),
                    int(cnts.get("purchase", 0)),
                    f"{product_rev_dict.get(pid, 0.0):.2f}",
                )
            )
        _write_csv(
            POWERBI_DIR / "top_products.csv",
            ["product_id", "views", "carts", "purchases", "revenue"],
            top_rows,
        )

        # -------------------------------------------------------------------
        # Helper for atomic PNG write
        # -------------------------------------------------------------------
        def _save_chart(fig, path: pathlib.Path):
            # Use a temporary filename with a proper image extension so Matplotlib can infer the format.
            # The temporary file ends with '.tmp.png' (or similar) and is later atomically replaced.
            tmp_path = path.with_suffix('.tmp.png')
            fig.savefig(tmp_path, format='png', bbox_inches='tight')
            plt.close(fig)
            os.replace(tmp_path, path)

        # 1. Event distribution bar chart
        fig1, ax1 = plt.subplots(figsize=(6, 4))
        ev_labels, ev_vals = zip(*sorted(event_counts.items()))
        ax1.bar(ev_labels, ev_vals, color="steelblue")
        ax1.set_title("Event Distribution")
        ax1.set_ylabel("Count")
        _save_chart(fig1, REPORTS_DIR / "event_distribution.png")

        # 2. Conversion funnel line chart (event‑level)
        fig2, ax2 = plt.subplots(figsize=(6, 4))
        funnel_vals = [event_counts.get("view", 0), event_counts.get("cart", 0), event_counts.get("purchase", 0)]
        ax2.plot(["view", "cart", "purchase"], funnel_vals, marker="o", linestyle="-")
        ax2.set_title("Conversion Funnel (Event‑Level)")
        ax2.set_ylabel("Count")
        _save_chart(fig2, REPORTS_DIR / "conversion_funnel.png")

        # 3. Cart abandonment pie chart
        fig3, ax3 = plt.subplots(figsize=(5, 5))
        labels = ["Abandoned", "Converted"]
        sizes = [abandoned_sessions, sessions_with_cart - abandoned_sessions]
        ax3.pie(sizes, labels=labels, autopct="%1.1f%%", colors=["tomato", "seagreen"], startangle=90)
        ax3.set_title(
            f"Cart Abandonment Rate ({abandonment_rate:.2%})\nPotential abandoned value: ${abandoned_value:,.2f}"
        )
        _save_chart(fig3, REPORTS_DIR / "cart_abandonment.png")

        # -------------------------------------------------------------------
        # Markdown report (includes both event‑level and session‑level rates)
        # -------------------------------------------------------------------
        report_path = REPORTS_DIR / "EDA_Report.md"
        tmp_report = report_path.with_suffix('.tmp')
        with tmp_report.open("w", encoding="utf-8") as f:
            f.write("# AbandoScope – Exploratory Data Analysis\n\n")
            f.write("## Methodology\n")
            f.write(
                "The analysis streams the cleaned CSV in *chunks* using pandas.  No full‑dataset\n"
                "structures are kept in memory; session‑level aggregates are stored in a\n"
                "disk‑based SQLite database to allow efficient upserts without loading all\n"
                "sessions simultaneously.  All outputs are written atomically via temporary\n"
                "files.\n\n"
            )
            f.write("## Key Findings\n")
            f.write(f"- Total rows processed: {total_rows_processed:,}\n")
            f.write(
                f"- Event distribution (view / cart / purchase): {event_counts.get('view',0):,} / "
                f"{event_counts.get('cart',0):,} / {event_counts.get('purchase',0):,}\n"
            )
            f.write(
                f"- Event‑level conversion rates: view→cart {event_funnel_rates['view_to_cart']:.2%}, "
                f"cart→purchase {event_funnel_rates['cart_to_purchase']:.2%}\n"
            )
            f.write(
                f"- Session‑level conversion rates: view→cart {session_funnel_rates['view_to_cart']:.2%}, "
                f"cart→purchase {session_funnel_rates['cart_to_purchase']:.2%}\n"
            )
            f.write(f"- Revenue from purchases: ${total_revenue:,.2f}\n")
            f.write(f"- Timestamp range: {min_timestamp} – {max_timestamp}\n")
            f.write(f"- Sessions with at least one view: {sessions_with_view:,}\n")
            f.write(f"- Sessions with at least one cart: {sessions_with_cart:,}\n")
            f.write(f"- Abandoned sessions (cart, no purchase): {abandoned_sessions:,} ({abandonment_rate:.2%})\n")
            f.write(
                f"- Potential abandoned‑cart value (sum of cart amounts for abandoned sessions): ${abandoned_value:,.2f}\n"
                "  *Note:* repeated cart events within a session inflate this figure; it is not actual lost revenue.\n\n"
            )
            f.write("### Category Performance\n")
            f.write("(see `category_performance.csv`)\n\n")
            f.write("### Brand Performance\n")
            f.write("(see `brand_performance.csv`)\n\n")
            f.write("### Top 20 Products by Purchase Revenue\n")
            f.write("(see `top_products.csv`)\n\n")
            f.write("## Visualisations\n")
            f.write("![Event distribution](/event_distribution.png)\n\n")
            f.write("![Conversion funnel](/conversion_funnel.png)\n\n")
            f.write("![Cart abandonment](/cart_abandonment.png)\n\n")
            f.write("## Recommendations\n")
            f.write(
                "- Prioritise marketing on categories/brands with high view‑to‑purchase conversion.\n"
                "- Investigate sessions that add items to cart but never purchase; consider targeted\n"
                "  remarketing or checkout‑flow improvements.\n"
                "- Monitor the synthetic `user_session` IDs (created during cleaning) for any\n"
                "  analysis that requires session continuity.\n"
            )
        os.replace(tmp_report, report_path)

        print("EDA completed successfully. Outputs written to:")
        print(f"  CSVs: {POWERBI_DIR}\n  Charts: {REPORTS_DIR}\n  Report: {report_path}")
        return 0
    finally:
        # Clean up temporary SQLite database regardless of success or failure
        conn.close()
        if TEMP_DB_PATH.exists():
            try:
                TEMP_DB_PATH.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
