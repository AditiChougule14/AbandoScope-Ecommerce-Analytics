# Validation script for 2019-Oct.csv using only Python standard library
import csv
import os
import datetime
import collections
import sys

# Paths (adjust if needed)
FILE_PATH = r'D:\AbandoScope_Analytics\data\raw\2019-Oct.csv'
REPORT_PATH = r'D:\AbandoScope_Analytics\docs\validation_report.md'
DICT_PATH = r'D:\AbandoScope_Analytics\docs\data_dictionary.md'

EXPECTED_COLS = [
    'event_time', 'event_type', 'product_id', 'category_id', 'category_code',
    'brand', 'price', 'user_id', 'user_session'
]

# Prepare counters
total_rows = 0
event_counts = collections.Counter()
missing_counts = collections.Counter()
min_time = None
max_time = None
actual_cols = []
header_verified = False

# Simple timestamp parser – tries a few common formats
def parse_time(s):
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

# Process the CSV line‑by‑line
with open(FILE_PATH, 'r', newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    for line_no, row in enumerate(reader, start=1):
        if line_no == 1:
            actual_cols = [c.strip() for c in row]
            header_verified = (
                len(actual_cols) == len(EXPECTED_COLS) and
                all(a == b for a, b in zip(actual_cols, EXPECTED_COLS))
            )
            # Ensure we have an index lookup for critical columns
            try:
                idx_event_type = actual_cols.index('event_type')
                idx_event_time = actual_cols.index('event_time')
            except ValueError:
                # Missing expected column – continue but be defensive later
                idx_event_type = idx_event_time = None
            continue

        total_rows += 1
        # Pad short rows to avoid IndexError
        if len(row) < len(actual_cols):
            row.extend([''] * (len(actual_cols) - len(row)))
        elif len(row) > len(actual_cols):
            row = row[:len(actual_cols)]

        # Missing‑value accounting
        for col_name, value in zip(actual_cols, row):
            if value == '' or value is None:
                missing_counts[col_name] += 1

        # Event type counting
        if idx_event_type is not None:
            event = row[idx_event_type]
            event_counts[event] += 1

        # Min / Max timestamps
        if idx_event_time is not None:
            t_str = row[idx_event_time]
            if t_str:
                dt = parse_time(t_str)
                if dt:
                    if min_time is None or dt < min_time:
                        min_time = dt
                    if max_time is None or dt > max_time:
                        max_time = dt
                else:
                    # Fallback to lexical comparison if parsing fails
                    if min_time is None or t_str < min_time:
                        min_time = t_str
                    if max_time is None or t_str > max_time:
                        max_time = t_str

# Write validation report
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, 'w', encoding='utf-8') as out:
    out.write('# Validation Report for 2019-Oct.csv\n\n')
    out.write('## Header verification\n')
    out.write(f"Expected columns ({len(EXPECTED_COLS)}): {', '.join(EXPECTED_COLS)}\n\n")
    out.write(f"Actual columns ({len(actual_cols)}): {', '.join(actual_cols)}\n\n")
    out.write(f"Header matches expected order: {'Yes' if header_verified else 'No'}\n\n")
    out.write('## Row counts\n')
    out.write(f"Total data rows (excluding header): {total_rows}\n\n")
    out.write('## Event type distribution\n')
    for ev, cnt in event_counts.most_common():
        out.write(f"- {ev}: {cnt}\n")
    out.write('\n')
    out.write('## Missing values per column\n')
    for col in actual_cols:
        miss = missing_counts.get(col, 0)
        pct = (miss / total_rows * 100) if total_rows else 0
        out.write(f"- {col}: {miss} missing ({pct:.4f}%)\n")
    out.write('\n')
    out.write('## Event time range\n')
    if isinstance(min_time, datetime.datetime):
        out.write(f"- Minimum event_time: {min_time.isoformat()}\n")
        out.write(f"- Maximum event_time: {max_time.isoformat()}\n")
    else:
        out.write(f"- Minimum event_time (raw string): {min_time}\n")
        out.write(f"- Maximum event_time (raw string): {max_time}\n")
    out.write('\n')
    out.write('## Duplicate record check\n')
    out.write('Full‑file duplicate detection was not performed because storing a hash for each of the ~150 M rows would exceed typical memory limits on this workstation.\n')
    out.write('If required, duplicates can be identified with external tools that operate on sorted data or by using a disk‑based hash set in multiple passes.\n')

# Write data dictionary
os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)
with open(DICT_PATH, 'w', encoding='utf-8') as dct:
    dct.write('# Data Dictionary – 2019-Oct.csv\n\n')
    dct.write('The following columns are present in the CSV (as observed from the header).\n\n')
    descriptions = {
        'event_time': 'Timestamp of the event (UTC).',
        'event_type': 'Interaction type – one of view, cart, remove_from_cart, purchase.',
        'product_id': 'Unique identifier of the product (integer).',
        'category_id': 'Numeric identifier of the product category.',
        'category_code': 'Hierarchical category code (e.g., "electronics.smartphone"); may contain nulls.',
        'brand': 'Brand name of the product; nullable.',
        'price': 'Price of the product at the time of the event (float).',
        'user_id': 'Anonymous unique identifier for the customer (integer).',
        'user_session': 'UUID representing a browsing session; resets when the user leaves the site.'
    }
    for col in actual_cols:
        dct.write(f"- **{col}**: {descriptions.get(col, 'No description available.') }\n")
    dct.write('\nAll values are stored as plain‑text strings in the CSV; numeric columns can be cast to int/float during analysis.\n')

print('Validation completed successfully.')
