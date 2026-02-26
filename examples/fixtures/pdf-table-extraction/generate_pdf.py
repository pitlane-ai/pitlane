#!/usr/bin/env python3
"""Generate sample-report.pdf with 4 tables across 3 pages.

Design rules:
- All tables use clean GRID lines (works well with pdfplumber)
- No merged header cells (SPAN)
- Includes special characters (TM, R symbols), ampersands, abbreviated currencies
- Page 1 has narrative text with numbers (to confuse naive extractors)
- Tables are structured to test multi-file output separation
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("sample-report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

# ── Page 1: Title + Executive Summary (no tables, but numbers in text) ──

story.append(Paragraph("Quarterly Business Report", styles["Title"]))
story.append(Spacer(1, 0.3 * inch))
story.append(Paragraph("Q4 2023 Performance Analysis", styles["Heading2"]))
story.append(Spacer(1, 0.2 * inch))

story.append(
    Paragraph(
        "This report provides a comprehensive overview of our company\u2019s performance "
        "throughout 2023. Total annual revenue reached $1.18M across 4 quarters, with "
        "Q4 achieving the highest quarterly revenue of $340,000. Operating expenses "
        "totaled $810,000 for the year, yielding a combined profit of $370,000.",
        styles["Normal"],
    )
)
story.append(Spacer(1, 0.2 * inch))

story.append(
    Paragraph(
        "Key highlights: 36% year-over-year revenue increase, 147 full-time employees "
        "across 5 departments, and expansion into 6 geographic territories. Our Widget\u2122 "
        "Pro and Gadget\u00ae Plus product lines contributed 62% of total unit sales. "
        "The following pages contain 4 detailed data tables covering financial "
        "performance, department allocation, regional sales, and product categories.",
        styles["Normal"],
    )
)
story.append(PageBreak())

# ── Page 2: Table 1 (Quarterly Revenue) + Table 2 (Department Allocation) ──

story.append(Paragraph("Financial Performance", styles["Heading1"]))
story.append(Spacer(1, 0.15 * inch))
story.append(
    Paragraph(
        "The table below summarizes our quarterly financial performance for 2023.",
        styles["Normal"],
    )
)
story.append(Spacer(1, 0.15 * inch))

# Table 1: Quarterly Financial Performance — 5 cols, 5 data rows + total row
table1_data = [
    ["Quarter", "Revenue ($)", "Expenses ($)", "Profit ($)", "Margin (%)"],
    ["Q1 2023", "$250,000", "$180,000", "$70,000", "28.0%"],
    ["Q2 2023", "$280,000", "$195,000", "$85,000", "30.4%"],
    ["Q3 2023", "$310,000", "$210,000", "$100,000", "32.3%"],
    ["Q4 2023", "$340,000", "$225,000", "$115,000", "33.8%"],
    ["FY 2023 Total", "$1,180,000", "$810,000", "$370,000", "31.4%"],
]

t1 = Table(
    table1_data, colWidths=[1.3 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.1 * inch]
)
t1.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]
    )
)
story.append(t1)
story.append(Spacer(1, 0.25 * inch))

story.append(
    Paragraph(
        "Note: All figures are in USD. Profit margins show steady improvement across quarters.",
        styles["Normal"],
    )
)
story.append(Spacer(1, 0.2 * inch))

story.append(Paragraph("Department resource allocation for 2023:", styles["Normal"]))
story.append(Spacer(1, 0.15 * inch))

# Table 2: Department Allocation — 4 cols, 5 data rows
table2_data = [
    ["Department", "Headcount", "Budget ($)", "Utilization (%)"],
    ["Engineering", "45", "$1.2M", "94%"],
    ["Sales & Marketing", "32", "$850K", "87%"],
    ["Operations", "28", "$620K", "91%"],
    ["Human Resources", "22", "$480K", "89%"],
    ["Finance & Legal", "20", "$410K", "92%"],
]

t2 = Table(table2_data, colWidths=[2 * inch, 1.3 * inch, 1.3 * inch, 1.5 * inch])
t2.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, 1), (-1, -1), colors.lightblue),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]
    )
)
story.append(t2)
story.append(PageBreak())

# ── Page 3: Table 3 (Regional Performance) + Table 4 (Product Category) ──

story.append(Paragraph("Regional Sales Performance", styles["Heading1"]))
story.append(Spacer(1, 0.15 * inch))
story.append(
    Paragraph(
        "Our regional analysis shows performance across all territories.",
        styles["Normal"],
    )
)
story.append(Spacer(1, 0.15 * inch))

# Table 3: Regional Performance — 6 cols, 6 data rows (one with negative growth)
table3_data = [
    ["Region", "Territory", "Sales ($)", "Growth (%)", "Top Product", "Units Sold"],
    ["North America", "US & Canada", "$450,000", "+12%", "Widget\u2122 Pro", "1,250"],
    ["South America", "Brazil & LATAM", "$380,000", "+8%", "Gadget\u00ae Plus", "980"],
    ["East Asia", "China & Japan", "$520,000", "+15%", "Device\u2122 Elite", "1,450"],
    ["Western Europe", "EU & UK", "$410,000", "+10%", "Tool\u00ae Max", "1,100"],
    ["Eastern Europe", "CIS & Balkans", "$185,000", "-3%", "Widget\u2122 Pro", "520"],
    ["Middle East", "GCC & Levant", "$210,000", "+5%", "Gadget\u00ae Plus", "630"],
]

t3 = Table(
    table3_data,
    colWidths=[1.2 * inch, 1.2 * inch, 1 * inch, 0.9 * inch, 1.2 * inch, 1 * inch],
)
t3.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]
    )
)
story.append(t3)
story.append(Spacer(1, 0.25 * inch))

story.append(Paragraph("Product Category Breakdown", styles["Heading2"]))
story.append(Spacer(1, 0.15 * inch))

# Table 4: Product Category Breakdown — 5 cols, hierarchical with sub-items and Grand Total
table4_data = [
    ["Category", "Product Line", "Units Sold", "Revenue ($)", "Market Share (%)"],
    ["Hardware", "Widget\u2122 Pro", "1,770", "$620K", "28%"],
    ["Hardware", "Device\u2122 Elite", "1,450", "$540K", "24%"],
    ["Software", "CloudSync\u2122", "3,200", "$380K", "17%"],
    ["Software", "DataFlow\u00ae", "2,800", "$320K", "14%"],
    ["Accessories", "Gadget\u00ae Plus", "1,610", "$210K", "9%"],
    ["Accessories", "Tool\u00ae Max", "1,100", "$180K", "8%"],
    ["Grand Total", "", "11,930", "$2.25M", "100%"],
]

t4 = Table(
    table4_data,
    colWidths=[1.2 * inch, 1.3 * inch, 1 * inch, 1.1 * inch, 1.3 * inch],
)
t4.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, 1), (-1, -2), colors.Color(0.9, 0.95, 0.9)),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]
    )
)
story.append(t4)
story.append(Spacer(1, 0.3 * inch))

story.append(
    Paragraph(
        "In conclusion, 2023 was a successful year with strong financial performance "
        "and balanced regional growth. All trademark symbols (\u2122, \u00ae) indicate "
        "registered products.",
        styles["Normal"],
    )
)

# Build PDF
doc.build(story)
print("Generated sample-report.pdf successfully")
