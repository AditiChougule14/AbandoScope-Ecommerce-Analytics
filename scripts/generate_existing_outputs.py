# -*- coding: utf-8 -*-
"""scripts/generate_existing_outputs.py

Recover visual outputs from the already‑generated Power BI CSV files.

* Does **not** read the massive cleaned CSV.
* Generates charts that can be built from the four CSVs present in
  `data/processed/powerbi/`.
* Saves PNG files atomically in `reports/eda/`.
* Produces a partial Markdown report that clearly notes the missing
  session‑level metrics (cart‑abandonment, abandonment value, session‑level
  conversion rates).
"""

import pathlib
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Configuration – reuse the same paths as the main EDA script
# ---------------------------------------------------------------------------
DATA_DIR = pathlib.Path("D:/AbandoScope_Analytics/data/processed")
POWERBI_DIR = DATA_DIR / "powerbi"
REPORTS_DIR = pathlib.Path("D:/AbandoScope_Analytics/reports/eda")

# Ensure the output directory exists
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _save_chart(fig, path: pathlib.Path) -> None:
    """Save a Matplotlib figure atomically as PNG.

    The temporary file ends with ``.tmp.png`` so Matplotlib can infer the
    format. After saving we close the figure and replace the target path.
    """
    tmp_path = path.with_suffix('.tmp.png')
    fig.savefig(tmp_path, format='png', bbox_inches='tight')
    plt.close(fig)
    os.replace(tmp_path, path)


def _write_report(content: str, path: pathlib.Path) -> None:
    """Write a Markdown report atomically (``.tmp`` -> final)."""
    tmp_path = path.with_suffix('.tmp')
    with tmp_path.open('w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp_path, path)


def main() -> int:
    # -----------------------------------------------------------------------
    # Load the CSVs that are already present
    # -----------------------------------------------------------------------
    try:
        events_df = pd.read_csv(POWERBI_DIR / "event_distribution.csv")
        category_df = pd.read_csv(POWERBI_DIR / "category_performance.csv")
        brand_df = pd.read_csv(POWERBI_DIR / "brand_performance.csv")
        top_products_df = pd.read_csv(POWERBI_DIR / "top_products.csv")
    except Exception as e:
        print(f"Failed to read required CSV files: {e}", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # 1️⃣ Event distribution bar chart
    # -----------------------------------------------------------------------
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    ax1.bar(events_df['event_type'], events_df['count'], color='steelblue')
    ax1.set_title('Event Distribution')
    ax1.set_ylabel('Count')
    _save_chart(fig1, REPORTS_DIR / "event_distribution.png")

    # -----------------------------------------------------------------------
    # 2️⃣ Event‑level conversion funnel (line chart)
    # -----------------------------------------------------------------------
    # Ensure ordering: view → cart → purchase
    funnel_order = ['view', 'cart', 'purchase']
    funnel_vals = [events_df.set_index('event_type').get('count').reindex(funnel_order).fillna(0).iloc[i] for i in range(3)]
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.plot(funnel_order, funnel_vals, marker='o', linestyle='-')
    ax2.set_title('Conversion Funnel (Event‑Level)')
    ax2.set_ylabel('Count')
    _save_chart(fig2, REPORTS_DIR / "conversion_funnel.png")

    # -----------------------------------------------------------------------
    # 3️⃣ Category performance bar chart (stacked view/cart/purchase)
    # -----------------------------------------------------------------------
    cat_counts = category_df[['category_code', 'views', 'carts', 'purchases']]
    cat_counts = cat_counts.set_index('category_code')
    fig3, ax3 = plt.subplots(figsize=(8, 5))
    cat_counts.plot(kind='bar', stacked=True, ax=ax3, colormap='tab20')
    ax3.set_title('Category Performance')
    ax3.set_ylabel('Count')
    ax3.legend(title='Event')
    _save_chart(fig3, REPORTS_DIR / "category_performance.png")

    # -----------------------------------------------------------------------
    # 4️⃣ Brand performance bar chart (stacked)
    # -----------------------------------------------------------------------
    brand_counts = brand_df[['brand', 'views', 'carts', 'purchases']]
    brand_counts = brand_counts.set_index('brand')
    fig4, ax4 = plt.subplots(figsize=(8, 5))
    brand_counts.plot(kind='bar', stacked=True, ax=ax4, colormap='tab20')
    ax4.set_title('Brand Performance')
    ax4.set_ylabel('Count')
    ax4.legend(title='Event')
    _save_chart(fig4, REPORTS_DIR / "brand_performance.png")

    # -----------------------------------------------------------------------
    # 5️⃣ Top‑20 products by purchase revenue (horizontal bar)
    # -----------------------------------------------------------------------
    # The CSV already contains only the top 20 rows sorted by revenue.
    fig5, ax5 = plt.subplots(figsize=(8, 6))
    ax5.barh(top_products_df['product_id'].astype(str), top_products_df['revenue'].astype(float))
    ax5.set_xlabel('Revenue (USD)')
    ax5.set_ylabel('Product ID')
    ax5.set_title('Top 20 Products by Purchase Revenue')
    ax5.invert_yaxis()  # Highest revenue on top
    _save_chart(fig5, REPORTS_DIR / "top_products.png")

    # -----------------------------------------------------------------------
    # 6️⃣ Partial EDA report (Markdown)
    # -----------------------------------------------------------------------
    report_path = REPORTS_DIR / "EDA_Report.md"
    report_md = """# Partial EDA Report (Generated from Existing CSVs)

## Methodology
The analysis was limited to the four Power BI CSV files that were already
produced by a previous full‑dataset run. No raw or cleaned transaction data
was read, ensuring a fast, memory‑efficient regeneration of visualisations.

## Available Results
- **Event distribution** and **event‑level conversion funnel** (view → cart → purchase) – charts generated from `event_distribution.csv`.
- **Category performance** – stacked bar chart of views, carts, purchases per category.
- **Brand performance** – stacked bar chart of views, carts, purchases per brand.
- **Top 20 products** – horizontal bar chart of purchase revenue.

## Missing Metrics
The original script also produced session‑level metrics (number of sessions
with view/cart/purchase, cart‑abandonment rate, potential abandoned‑cart
value). Those values were held only in a temporary SQLite database that was
removed at the end of the full run, so they cannot be reconstructed from the
CSV files alone. Consequently:

- **Cart‑abandonment rate** and **abandoned‑cart value** are *not available*.
- Session‑level conversion rates are *unavailable*.

*No values have been invented; the report explicitly states the gaps.*

## Figures
The following PNG files have been created in this directory:
- `event_distribution.png`
- `conversion_funnel.png`
- `category_performance.png`
- `brand_performance.png`
- `top_products.png`

---
*Generated by `scripts/generate_existing_outputs.py` on {timestamp}.*
""".format(timestamp=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'))
    _write_report(report_md, report_path)

    print("Generated charts and partial report:")
    for f in ["event_distribution.png", "conversion_funnel.png", "category_performance.png",
              "brand_performance.png", "top_products.png", "EDA_Report.md"]:
        print(f"  {REPORTS_DIR / f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
