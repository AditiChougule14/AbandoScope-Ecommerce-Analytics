import pandas as pd, sys
csv_path = r'D:\AbandoScope_Analytics\data\processed\clean_2019_oct.csv'
chunks = pd.read_csv(csv_path, chunksize=200000, low_memory=False)
missing_counts = {'view':0, 'cart':0, 'purchase':0}
missing_revenue = 0.0
for chunk in chunks:
    # Ensure brand column is string type
    brand = chunk['brand'].astype(str)
    # Identify rows where brand is NaN, empty, or whitespace-only after stripping
    mask = brand.isna() | (brand.str.strip() == '') | (brand == 'nan')
    # Also treat case where brand is actual NaN (float), but after astype string becomes 'nan'
    # Use original column for NaNs
    mask = mask | chunk['brand'].isna()
    subset = chunk[mask]
    if not subset.empty:
        # Count events
        ev_counts = subset['event_type'].value_counts()
        for ev in ['view', 'cart', 'purchase']:
            missing_counts[ev] += ev_counts.get(ev, 0)
        # Sum revenue for purchase events
        purchase_rows = subset[subset['event_type'] == 'purchase']
        missing_revenue += purchase_rows['price'].sum()
print('Missing brand rows summary:')
print(missing_counts)
print('Missing purchase revenue:', missing_revenue)
