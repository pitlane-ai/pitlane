# PDF Table Extraction Eval

Compares a baseline assistant against one equipped with the Anthropic PDF skill on a multi-table PDF extraction task.

## The Challenge

`sample-report.pdf` contains a business report with:

- **3 pages** with mixed content (text and tables)
- **4 tables** with realistic complexity:
  1. **Quarterly Financial Performance** (Page 2) — 5 columns, 5 data rows + total row
  2. **Department Allocation** (Page 2) — 4 columns, 5 data rows with abbreviated currencies ($1.2M, $850K)
  3. **Regional Performance** (Page 3) — 6 columns, 6 data rows with one negative growth (-3%)
  4. **Product Category Breakdown** (Page 3) — 5 columns, hierarchical categories with Grand Total

**Realistic complexity:** multiple tables across pages with narrative text between them, special characters (TM, R symbols), ampersands, abbreviated currencies, and a page-1 executive summary with numbers (to confuse naive extractors).

## What This Measures

Both baseline and skill-equipped assistants typically pass all 18 assertions — the model is competent enough at PDF table extraction without the skill. The value of the skill shows up in **efficiency metrics**:

| Metric | Baseline (typical) | With Skill (typical) |
|--------|--------------------|-----------------------|
| Wall time | 55–169 s | 25–60 s |
| Tool calls | Higher | Lower |
| Token usage | Higher | Lower |

The timeout is set to 90 s. The skill version completes comfortably within this limit, while some baseline runs time out — producing a concrete score difference.

## Assertions (18 checks)

1. **File existence** (5): table_1.csv through table_4.csv + extraction_summary.txt
2. **Column counts** (4): each table must have the correct number of columns
3. **Row counts** (2): tables must have minimum expected data rows
4. **Content checks** (6): specific values must appear in the correct file
5. **Validation script** (1): structural validation of all files

## Running the Eval

```bash
# Single run
uv run pitlane run examples/pdf-table-extraction-eval.yaml

# Recommended: 3 repeats to capture variance in time/tokens
uv run pitlane run examples/pdf-table-extraction-eval.yaml --repeat 3

# Baseline only
uv run pitlane run examples/pdf-table-extraction-eval.yaml --only-assistants opencode-baseline
```

## Regenerating the PDF

```bash
cd examples/fixtures/pdf-table-extraction
uv run python generate_pdf.py
```

## Files

- `sample-report.pdf` — the test PDF with 4 tables
- `generate_pdf.py` — script to regenerate the PDF
- `validate_extraction.py` — structural validation script for the 4 CSV files
- `refs/expected-tables.csv` — reference output showing expected format
