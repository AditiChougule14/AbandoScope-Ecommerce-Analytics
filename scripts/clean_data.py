# -*- coding: utf-8 -*-
"""clean_data.py

Streaming data‑cleaning script for the REES46 October‑2019 dataset.

* Reads the raw CSV line‑by‑line using the standard‑library ``csv`` module –
  quoting, embedded commas and double‑quotes are handled automatically.
* Replaces missing values:
    - ``category_code`` → ``UNKNOWN``
    - ``brand``         → ``NO_BRAND``
    - ``user_session``  → a synthetic ID (``synthetic‑session‑1`` or
      ``synthetic‑session‑2``).  The synthetic IDs and their original row numbers
      are written to ``session_audit.tsv`` for later reference.
* Validates that every data row contains exactly **9** fields; if not, the script
  aborts and reports the offending row number.
* Tracks statistics (row count, event‑type distribution, missing‑value counts,
  timestamp range) while streaming.
* Writes three artefacts **to temporary files** first and renames them to the
  final names only after all verification checks succeed:
    - ``clean_2019_oct.csv``   → written to ``data\\processed``.
    - ``session_audit.tsv``    → written to ``docs``.
    - ``cleaning_report.md``   → written to ``docs``.
* After processing, the script verifies that the cleaned data matches the
  expected totals (row count, event counts, min/max timestamps, synthetic
  session count, audit entry count).  If any check fails, the script reports the
  discrepancy, removes all temporary files, and exits with a non‑zero status.
* The original raw CSV is never modified.
"""

import csv
import os
import sys
import shutil
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration (adjust if the project layout changes)
# ---------------------------------------------------------------------------
RAW_CSV = r"D:\\AbandoScope_Analytics\\data\\raw\\2019-Oct.csv"
PROCESSED_DIR = r"D:\\AbandoScope_Analytics\\data\\processed"
FINAL_CLEAN_CSV = os.path.join(PROCESSED_DIR, "clean_2019_oct.csv")
DOCS_DIR = r"D:\\AbandoScope_Analytics\\docs"
FINAL_SESSION_AUDIT = os.path.join(DOCS_DIR, "session_audit.tsv")
FINAL_CLEANING_REPORT = os.path.join(DOCS_DIR, "cleaning_report.md")

# Temporary filenames (same directory, .tmp suffix)
TMP_CLEAN_CSV = FINAL_CLEAN_CSV + ".tmp"
TMP_SESSION_AUDIT = FINAL_SESSION_AUDIT + ".tmp"
TMP_CLEANING_REPORT = FINAL_CLEANING_REPORT + ".tmp"

# Expected values for verification
EXPECTED_TOTAL_ROWS = 42_448_764
EXPECTED_COUNTS = {"view": 40_779_399, "cart": 926_516, "purchase": 742_849}
EXPECTED_MIN_TIME = "2019-10-01 00:00:00 UTC"
EXPECTED_MAX_TIME = "2019-10-31 23:59:59 UTC"

EXPECTED_SYNTHETIC_SESSIONS = 2

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def ensure_dir(path):
    """Create the directory if it does not exist."""
    os.makedirs(path, exist_ok=True)

def enough_free_space(source_path, target_dir, factor=1.2):
    """Return True if ``target_dir`` has at least ``factor``× the size of
    ``source_path`` free on disk.
    """
    src_size = os.path.getsize(source_path)
    total, used, free = shutil.disk_usage(target_dir)
    return free >= int(src_size * factor)

def safe_remove(path):
    """Remove a file if it exists, ignore errors."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def atomic_rename(tmp_path, final_path):
    """Rename a temporary file to its final name atomically.
    Returns True on success, False on failure.
    """
    try:
        os.replace(tmp_path, final_path)
        return True
    except Exception as e:
        sys.stderr.write(f"Failed to rename {tmp_path} -> {final_path}: {e}\n")
        return False

# ---------------------------------------------------------------------------
# Main cleaning routine
# ---------------------------------------------------------------------------
def main():
    # Verify source exists
    if not os.path.isfile(RAW_CSV):
        sys.stderr.write(f"Error: source CSV not found at {RAW_CSV}\n")
        sys.exit(1)

    # Ensure output directories exist
    ensure_dir(PROCESSED_DIR)
    ensure_dir(DOCS_DIR)

    # Check free disk space before creating any temp files
    if not enough_free_space(RAW_CSV, PROCESSED_DIR):
        sys.stderr.write(
            f"Error: not enough free disk space in {PROCESSED_DIR}. "
            "Need at least 1.2× source size.\n"
        )
        sys.exit(1)

    # Abort if any final output file already exists (do not overwrite)
    if any(os.path.exists(p) for p in (FINAL_CLEAN_CSV, FINAL_SESSION_AUDIT, FINAL_CLEANING_REPORT)):
        sys.stderr.write(
            "Error: one or more final output files already exist. "
            "Remove or rename them before running the cleaning script.\n"
        )
        sys.exit(1)

    # Counters for verification
    total_rows = 0
    event_counts = defaultdict(int)
    missing_counts = defaultdict(int)
    min_time = ""
    max_time = ""
    synthetic_session_counter = 0

    # Open temporary files using context managers for safety
    try:
        with open(TMP_SESSION_AUDIT, "w", encoding="utf-8", newline="\n") as audit_f, \
             open(TMP_CLEAN_CSV, "w", encoding="utf-8", newline="") as out_f:

            audit_f.write("row_number\tsynthetic_session_id\n")  # header
            writer = None  # will be set after reading header

            # Process the raw CSV inside its own try/except to capture any error
            try:
                with open(RAW_CSV, "r", encoding="utf-8", newline="") as in_f:
                    reader = csv.reader(in_f)
                    header = next(reader)  # keep original order
                    if len(header) != 9:
                        sys.stderr.write(
                            f"Error: header contains {len(header)} fields, expected 9.\n"
                        )
                        raise ValueError("Header field count incorrect")

                    writer = csv.writer(out_f, quoting=csv.QUOTE_MINIMAL)
                    writer.writerow(header)

                    # Column indices (zero‑based)
                    idx_category_code = header.index("category_code")
                    idx_brand = header.index("brand")
                    idx_user_session = header.index("user_session")
                    idx_event_type = header.index("event_type")
                    idx_event_time = header.index("event_time")

                    for row in reader:
                        total_rows += 1

                        # ----- Row length validation -----
                        if len(row) != 9:
                            sys.stderr.write(
                                f"Error: row {total_rows} has {len(row)} fields, expected 9.\n"
                            )
                            raise ValueError("Row length validation failed")

                        # ----- Missing‑value handling -----
                        if not row[idx_category_code]:
                            row[idx_category_code] = "UNKNOWN"
                            missing_counts["category_code"] += 1
                        # ----- Brand missing‑value handling -----
                        brand_val = row[idx_brand]
                        if brand_val is None:
                            brand_val = ""
                        brand_val = str(brand_val).strip()
                        if not brand_val:
                            row[idx_brand] = "NO_BRAND"
                            missing_counts["brand"] += 1
                        else:
                            row[idx_brand] = brand_val
                        if not row[idx_user_session]:
                            synthetic_session_counter += 1
                            synthetic_id = f"synthetic-session-{synthetic_session_counter}"
                            row[idx_user_session] = synthetic_id
                            audit_f.write(f"{total_rows}\t{synthetic_id}\n")
                            missing_counts["user_session"] += 1

                        # ----- Event‑type counting -----
                        event_type = row[idx_event_type]
                        event_counts[event_type] += 1

                        # ----- Timestamp range (lexicographic) -----
                        t_str = row[idx_event_time]
                        if t_str:
                            if not min_time or t_str < min_time:
                                min_time = t_str
                            if not max_time or t_str > max_time:
                                max_time = t_str

                        # Write cleaned row (proper CSV quoting handled by writer)
                        writer.writerow(row)

                        # ----- Progress output -----
                        if total_rows % 1_000_000 == 0:
                            print(f"Processed {total_rows:,} rows ...")
            except Exception as e:
                # Any error inside CSV processing – ensure temp files are removed
                sys.stderr.write(f"Processing error: {e}\n")
                raise  # re‑raise to outer block for cleanup
    except Exception:
        # Cleanup all temporary files on any failure
        safe_remove(TMP_SESSION_AUDIT)
        safe_remove(TMP_CLEAN_CSV)
        safe_remove(TMP_CLEANING_REPORT)
        sys.exit(1)

    # -------------------------------------------------------------------
    # Verification after full pass
    # -------------------------------------------------------------------
    verification_errors = []

    if total_rows != EXPECTED_TOTAL_ROWS:
        verification_errors.append(
            f"Row count mismatch: expected {EXPECTED_TOTAL_ROWS:,}, got {total_rows:,}"
        )
    for ev, exp_cnt in EXPECTED_COUNTS.items():
        actual = event_counts.get(ev, 0)
        if actual != exp_cnt:
            verification_errors.append(
                f"Event '{ev}' count mismatch: expected {exp_cnt:,}, got {actual:,}"
            )
    if min_time != EXPECTED_MIN_TIME:
        verification_errors.append(
            f"Minimum timestamp mismatch: expected '{EXPECTED_MIN_TIME}', got '{min_time}'"
        )
    if max_time != EXPECTED_MAX_TIME:
        verification_errors.append(
            f"Maximum timestamp mismatch: expected '{EXPECTED_MAX_TIME}', got '{max_time}'"
        )
    if synthetic_session_counter != EXPECTED_SYNTHETIC_SESSIONS:
        verification_errors.append(
            f"Synthetic user_session count mismatch: expected {EXPECTED_SYNTHETIC_SESSIONS}, got {synthetic_session_counter}"
        )

    # Verify audit file contains exactly the expected number of data rows (exclude header)
    try:
        with open(TMP_SESSION_AUDIT, "r", encoding="utf-8") as audit_check_f:
            audit_lines = audit_check_f.readlines()
            audit_data_rows = len(audit_lines) - 1  # subtract header line
            if audit_data_rows != EXPECTED_SYNTHETIC_SESSIONS:
                verification_errors.append(
                    f"Session audit entry count mismatch: expected {EXPECTED_SYNTHETIC_SESSIONS}, got {audit_data_rows}"
                )
    except Exception as e:
        verification_errors.append(f"Failed to read audit file for verification: {e}")

    # If any verification failed, write a failure report and abort (remove temp CSV)
    if verification_errors:
        with open(TMP_CLEANING_REPORT, "w", encoding="utf-8", newline="\n") as rpt:
            rpt.write("# Cleaning Report – Verification Failed\n\n")
            for line in verification_errors:
                rpt.write(f"- {line}\n")
            rpt.write("\nThe cleaning process aborted; no final output files were created.\n")
        # Remove successful but unverified data file
        safe_remove(TMP_CLEAN_CSV)
        safe_remove(TMP_SESSION_AUDIT)
        sys.exit(1)

    # -------------------------------------------------------------------
    # Write the successful cleaning report
    # -------------------------------------------------------------------
    with open(TMP_CLEANING_REPORT, "w", encoding="utf-8", newline="\n") as rpt:
        rpt.write("# Cleaning Report – 2019‑Oct.csv\n\n")
        rpt.write(f"**Source file:** `{RAW_CSV}`\n\n")
        rpt.write(f"**Rows processed:** {total_rows:,}\n\n")
        rpt.write("## Missing‑value replacements\n\n")
        for col, cnt in missing_counts.items():
            rpt.write(f"- {col}: {cnt:,} replacements\n")
        rpt.write("\n## Event‑type distribution\n\n")
        for ev, cnt in sorted(event_counts.items(), key=lambda x: x[1], reverse=True):
            rpt.write(f"- {ev}: {cnt:,}\n")
        rpt.write("\n## Timestamp range (raw strings)\n\n")
        rpt.write(f"- Minimum event_time: {min_time}\n")
        rpt.write(f"- Maximum event_time: {max_time}\n\n")
        rpt.write(
            "**Note:** Full‑file duplicate detection was **deferred** and not performed in this cleaning pass.\n"
        )

    # -------------------------------------------------------------------
    # Promote temporary files to final names – each rename is atomic individually.
    # If any rename fails, report which files succeeded.
    # -------------------------------------------------------------------
    promoted = []
    if atomic_rename(TMP_CLEAN_CSV, FINAL_CLEAN_CSV):
        promoted.append("clean CSV")
    if atomic_rename(TMP_SESSION_AUDIT, FINAL_SESSION_AUDIT):
        promoted.append("session audit")
    if atomic_rename(TMP_CLEANING_REPORT, FINAL_CLEANING_REPORT):
        promoted.append("cleaning report")

    if len(promoted) != 3:
        sys.stderr.write(
            f"Error: not all files were promoted successfully. Files promoted: {', '.join(promoted)}. "
            "Cleaning considered failed.\n"
        )
        # Attempt to clean any leftover temp files
        safe_remove(TMP_CLEAN_CSV)
        safe_remove(TMP_SESSION_AUDIT)
        safe_remove(TMP_CLEANING_REPORT)
        sys.exit(1)

    print("\nCleaning completed successfully. All verification checks passed.\n")
    print(f"* Raw CSV (untouched): {RAW_CSV}")
    print(f"* Clean CSV:          {FINAL_CLEAN_CSV}")
    print(f"* Session audit:      {FINAL_SESSION_AUDIT}")
    print(f"* Cleaning report:    {FINAL_CLEANING_REPORT}\n")

if __name__ == "__main__":
    main()
