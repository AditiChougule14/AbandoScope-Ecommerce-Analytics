"""Regenerate only the brand_performance.csv Power BI file.

The script reads the already‑cleaned CSV (data/processed/clean_2019_oct.csv) in
chunks to avoid loading the 5.85 GB file into memory, normalises the *brand*
values in the same way as the main EDA pipeline, aggregates event counts and
purchase revenue per brand, and writes a fresh CSV to data/processed/powerbi.
It also backs up the existing file before overwriting and verifies that the
generated totals match the event‑distribution totals and that revenue aligns
with the category totals (within a small tolerance).
"""

import pathlib, shutil, sys
import pandas as pd
import csv



# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RAW_CLEANED_CSV = pathlib.Path(r"D:\AbandoScope_Analytics\data\processed\clean_2019_oct.csv")
POWERBI_DIR = pathlib.Path(r"D:\AbandoScope_Analytics\data\processed\powerbi")
BRAND_CSV = POWERBI_DIR / "brand_performance.csv"
EVENT_CSV = POWERBI_DIR / "event_distribution.csv"
CATEGORY_CSV = POWERBI_DIR / "category_performance.csv"
CHUNK_SIZE = 200_000

def backup_file(path: pathlib.Path) -> None:
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        print(f"Backup created: {backup}")

def normalize_brand(series: pd.Series) -> pd.Series:
    # Fill NaN, strip whitespace, and treat empty strings as NO_BRAND
    s = series.fillna('').astype(str).str.strip()
    s = s.replace('', 'NO_BRAND')
    s = s.replace('nan', 'NO_BRAND')
    s = s.replace('None', 'NO_BRAND')
    return s


def main():
    if not RAW_CLEANED_CSV.is_file():
        sys.stderr.write(f"Error: cleaned CSV not found at {RAW_CLEANED_CSV}\n")
        sys.exit(1)

    # Backup existing brand CSV
    backup_file(BRAND_CSV)

    brand_agg = None  # DataFrame of counts per brand/event_type
    brand_rev = {}

    csv_iter = pd.read_csv(
        RAW_CLEANED_CSV,
        chunksize=CHUNK_SIZE,
        dtype={
            "event_type": "category",
            "brand": "object",
            "price": "float64",
        },
        low_memory=False,
    )

    for chunk_idx, chunk in enumerate(csv_iter, start=1):
        # Normalise brand values
        chunk["brand"] = normalize_brand(chunk["brand"])
        # Ensure any remaining NaN is replaced
        chunk["brand"] = chunk["brand"].fillna("NO_BRAND")


        # Counts per brand/event_type
        grp = chunk.groupby(["brand", "event_type"]).size().unstack(fill_value=0)
        if brand_agg is None:
            brand_agg = grp.copy()
        else:
            brand_agg = brand_agg.add(grp, fill_value=0)

        # Purchase revenue per brand
        purchase_rev = (
            chunk[chunk["event_type"] == "purchase"].groupby("brand")["price"].sum()
        )
        for br, rev in purchase_rev.items():
            brand_rev[br] = brand_rev.get(br, 0.0) + float(rev)

        print(f"Processed chunk {chunk_idx}")

    # ---------------------------------------------------------------------
    # Write the brand CSV atomically (temp file then rename)
    # ---------------------------------------------------------------------
    temp_path = BRAND_CSV.with_suffix('.tmp')
    with temp_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow(['brand','views','carts','purchases','revenue'])
        for brand, cnts in brand_agg.iterrows():
            views = int(cnts.get('view', 0))
            carts = int(cnts.get('cart', 0))
            purchases = int(cnts.get('purchase', 0))
            revenue = f"{brand_rev.get(brand, 0.0):.2f}"
            writer.writerow([brand, views, carts, purchases, revenue])

    shutil.move(temp_path, BRAND_CSV)
    print(f"Regenerated brand CSV at {BRAND_CSV}")

    # ---------------------------------------------------------------------
    # Verification
    # ---------------------------------------------------------------------
    # Event totals
    ev_df = pd.read_csv(EVENT_CSV)
    ev_totals = ev_df.set_index('event_type')['count'].to_dict()

    # Brand totals
    br_df = pd.read_csv(BRAND_CSV)
    br_totals = {
        'view': br_df['views'].sum(),
        'cart': br_df['carts'].sum(),
        'purchase': br_df['purchases'].sum(),
        'revenue': br_df['revenue'].astype(float).sum(),
    }

    # Category revenue (for tolerance comparison)
    cat_df = pd.read_csv(CATEGORY_CSV)
    cat_rev_total = cat_df['revenue'].astype(float).sum()

    print('\n--- Verification ---')
    print(f"Event totals:   views={ev_totals.get('view'):,}, carts={ev_totals.get('cart'):,}, purchases={ev_totals.get('purchase'):,}")
    print(f"Brand totals:   views={br_totals['view']:,}, carts={br_totals['cart']:,}, purchases={br_totals['purchase']:,}, revenue={br_totals['revenue']:.2f}")
    print(f"Category rev total: {cat_rev_total:.2f}")

    view_match = ev_totals.get('view') == br_totals['view']
    cart_match = ev_totals.get('cart') == br_totals['cart']
    purchase_match = ev_totals.get('purchase') == br_totals['purchase']
    revenue_match = abs(cat_rev_total - br_totals['revenue']) < 0.01  # tolerance

    print('Matches:')
    print(f"  Views:    {view_match}")
    print(f"  Carts:    {cart_match}")
    print(f"  Purchases:{purchase_match}")
    print(f"  Revenue~: {revenue_match} (diff={abs(cat_rev_total - br_totals['revenue']):.2f})")

if __name__ == "__main__":
    main()
