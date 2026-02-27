#!/usr/bin/env python3
"""Validate that all four tables were extracted into separate CSV files correctly."""

import csv
import os
import sys

errors = []


def check_csv(
    filename, expected_cols, min_data_rows, required_headers, required_values
):
    """Validate a single CSV file. Appends to global errors list."""
    if not os.path.exists(filename):
        errors.append(f"{filename}: file not found")
        return

    try:
        with open(filename, "r") as f:
            rows = list(csv.reader(f))
    except Exception as e:
        errors.append(f"{filename}: failed to parse CSV: {e}")
        return

    if len(rows) < 1:
        errors.append(f"{filename}: file is empty")
        return

    header = rows[0]

    # Check for None/empty headers
    bad_headers = [h for h in header if not h or h.lower() == "none"]
    if bad_headers:
        errors.append(f"{filename}: header contains None/empty values: {header}")

    # Check column count
    if len(header) != expected_cols:
        errors.append(
            f"{filename}: expected {expected_cols} columns, got {len(header)}: {header}"
        )

    # Check minimum data rows (excluding header)
    data_rows = [r for r in rows[1:] if any(cell.strip() for cell in r)]
    if len(data_rows) < min_data_rows:
        errors.append(
            f"{filename}: expected >= {min_data_rows} data rows, got {len(data_rows)}"
        )

    # Check required header keywords
    header_text = " ".join(header).lower()
    for kw in required_headers:
        if kw.lower() not in header_text:
            errors.append(f"{filename}: missing required header keyword '{kw}'")

    # Check required data values
    content = "\n".join([",".join(r) for r in rows])
    for val in required_values:
        if val not in content:
            errors.append(f"{filename}: missing required value '{val}'")


# Table 1: Quarterly Financial Performance — 5 cols, 5+ data rows
check_csv(
    "table_1.csv",
    expected_cols=5,
    min_data_rows=5,
    required_headers=["Quarter", "Revenue"],
    required_values=["Q1 2023", "Q4 2023"],
)

# Table 2: Department Allocation — 4 cols, 5 data rows
check_csv(
    "table_2.csv",
    expected_cols=4,
    min_data_rows=5,
    required_headers=["Department"],
    required_values=["Engineering", "Sales"],
)

# Table 3: Regional Performance — 6 cols, 6 data rows
check_csv(
    "table_3.csv",
    expected_cols=6,
    min_data_rows=6,
    required_headers=["Region", "Territory"],
    required_values=["North America", "East Asia"],
)

# Table 4: Product Category Breakdown — 5 cols, 7+ data rows (6 items + Grand Total)
check_csv(
    "table_4.csv",
    expected_cols=5,
    min_data_rows=7,
    required_headers=["Category"],
    required_values=["Grand Total", "Hardware"],
)

# Report results
if errors:
    print(f"FAIL: {len(errors)} validation error(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("PASS: All four tables extracted and validated successfully")
    sys.exit(0)
