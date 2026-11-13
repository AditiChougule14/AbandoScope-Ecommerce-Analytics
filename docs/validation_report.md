# Validation Report for 2019-Oct.csv

## Header verification
Expected columns (9): event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session
Actual columns   (9): event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session
Header matches expected order: Yes

## Row counts
Total data rows (excluding header): 42448764
Malformed rows (wrong column count): 0

## Event type distribution
- view: 40779399
- cart: 926516
- purchase: 742849

## Missing values per column
- event_time: 0 missing (0.0000%) (out of 42448764 valid rows)
- event_type: 0 missing (0.0000%) (out of 42448764 valid rows)
- product_id: 0 missing (0.0000%) (out of 42448764 valid rows)
- category_id: 0 missing (0.0000%) (out of 42448764 valid rows)
- category_code: 13515609 missing (31.8398%) (out of 42448764 valid rows)
- brand: 6113008 missing (14.4009%) (out of 42448764 valid rows)
- price: 0 missing (0.0000%) (out of 42448764 valid rows)
- user_id: 0 missing (0.0000%) (out of 42448764 valid rows)
- user_session: 2 missing (0.0000%) (out of 42448764 valid rows)

## Event time range
- Minimum event_time (raw string): 2019-10-01 00:00:00 UTC
- Maximum event_time (raw string): 2019-10-31 23:59:59 UTC

## Duplicate record check
Full-file duplicate detection was not performed because storing a hash for each of the ~150 M rows would exceed typical memory limits on this workstation.
If required, duplicates can be identified with external tools that operate on sorted data or by using a disk-based hash set in multiple passes.
