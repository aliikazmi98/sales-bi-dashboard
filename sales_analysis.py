"""
Sales BI Dashboard — Main Analysis Script
==========================================
Dataset  : Superstore Retail Sales (train.csv)
Database : SQLite (sales_database.db)
Outputs  :
    - sales_database.db
    - tableau_sales.csv
    - mom_trends.csv
    - regional_rankings.csv
    - cohort_analysis.csv
    - model_summary.txt
"""

import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CSV_PATH    = "/Users/hp/Documents/freelance-projects/train.csv"
DB_PATH     = os.path.join(SCRIPT_DIR, "sales_database.db")
SQL_PATH    = os.path.join(SCRIPT_DIR, "sales_queries.sql")
OUT_TABLEAU = os.path.join(SCRIPT_DIR, "tableau_sales.csv")
OUT_MOM     = os.path.join(SCRIPT_DIR, "mom_trends.csv")
OUT_REGION  = os.path.join(SCRIPT_DIR, "regional_rankings.csv")
OUT_COHORT  = os.path.join(SCRIPT_DIR, "cohort_analysis.csv")
OUT_SUMMARY = os.path.join(SCRIPT_DIR, "model_summary.txt")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — LOAD & CLEAN DATA
# ══════════════════════════════════════════════════════════════════════════════

def load_and_clean(csv_path: str) -> pd.DataFrame:
    print("[1/5] Loading CSV …")
    df = pd.read_csv(csv_path)
    original_rows = len(df)

    # ── Column names: snake_case ───────────────────────────────────────────────
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    # ── Date parsing (handles both MM/DD/YYYY and DD/MM/YYYY via dayfirst) ─────
    for col in ["order_date", "ship_date"]:
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    # Drop rows where order_date is unparseable (should be zero)
    date_nulls = df["order_date"].isna().sum()
    if date_nulls:
        print(f"   Dropping {date_nulls} rows with unparseable order_date.")
        df = df.dropna(subset=["order_date"])

    # ── Missing postal codes: fill with 'UNKNOWN' ──────────────────────────────
    df["postal_code"] = df["postal_code"].fillna(-1).astype(int).astype(str)
    df["postal_code"] = df["postal_code"].replace("-1", "UNKNOWN")

    # ── Derived columns ────────────────────────────────────────────────────────
    df["order_year"]       = df["order_date"].dt.year
    df["order_month"]      = df["order_date"].dt.month
    df["order_month_name"] = df["order_date"].dt.strftime("%B")
    df["order_quarter"]    = df["order_date"].dt.quarter
    df["order_yearmonth"]  = df["order_date"].dt.strftime("%Y-%m")
    df["ship_days"]        = (df["ship_date"] - df["order_date"]).dt.days

    # ── Ensure sales is numeric and positive ───────────────────────────────────
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce")
    neg_sales = (df["sales"] <= 0).sum()
    if neg_sales:
        print(f"   Flagging {neg_sales} rows with non-positive sales.")
    df = df[df["sales"] > 0].copy()

    # ── Remove exact duplicates ────────────────────────────────────────────────
    dupes = df.duplicated().sum()
    if dupes:
        print(f"   Removing {dupes} exact duplicate rows.")
        df = df.drop_duplicates()

    cleaned_rows = len(df)
    print(f"   Rows: {original_rows:,} → {cleaned_rows:,} after cleaning.")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — LOAD INTO SQLITE
# ══════════════════════════════════════════════════════════════════════════════

def load_to_sqlite(df: pd.DataFrame, db_path: str) -> sqlite3.Connection:
    print("[2/5] Loading into SQLite …")

    # Store dates as ISO strings so SQLite date functions work
    df_sql = df.copy()
    df_sql["order_date"] = df_sql["order_date"].dt.strftime("%Y-%m-%d")
    df_sql["ship_date"]  = df_sql["ship_date"].dt.strftime("%Y-%m-%d")

    conn = sqlite3.connect(db_path)
    df_sql.to_sql("sales", conn, if_exists="replace", index=False)

    # Useful indexes for query performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_date   ON sales(order_date);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_customer_id  ON sales(customer_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_region       ON sales(region);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_category     ON sales(category);")
    conn.commit()

    row_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    print(f"   Inserted {row_count:,} rows into 'sales' table.")
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — RUN SQL ANALYSES
# ══════════════════════════════════════════════════════════════════════════════

def run_analyses(conn: sqlite3.Connection) -> dict:
    print("[3/5] Running SQL analyses …")
    results = {}

    # ── 3a. Summary metrics ────────────────────────────────────────────────────
    results["summary"] = pd.read_sql_query("""
        SELECT
            COUNT(DISTINCT order_id)    AS total_orders,
            COUNT(DISTINCT customer_id) AS total_customers,
            COUNT(*)                    AS total_line_items,
            ROUND(SUM(sales), 2)        AS total_revenue,
            ROUND(AVG(sales), 2)        AS avg_line_value,
            MIN(order_date)             AS first_order_date,
            MAX(order_date)             AS last_order_date
        FROM sales
    """, conn)

    # ── 3b. Regional rankings ──────────────────────────────────────────────────
    results["regional"] = pd.read_sql_query("""
        WITH region_metrics AS (
            SELECT
                region,
                COUNT(DISTINCT order_id)    AS orders,
                COUNT(DISTINCT customer_id) AS customers,
                ROUND(SUM(sales), 2)        AS revenue,
                ROUND(AVG(sales), 2)        AS avg_sale
            FROM sales
            GROUP BY region
        )
        SELECT
            region,
            orders,
            customers,
            revenue,
            avg_sale,
            RANK() OVER (ORDER BY revenue DESC)                        AS revenue_rank,
            ROUND(revenue * 100.0 / SUM(revenue) OVER (), 2)          AS revenue_pct
        FROM region_metrics
        ORDER BY revenue_rank
    """, conn)

    # ── 3c. Top 10 products ────────────────────────────────────────────────────
    results["top10_products"] = pd.read_sql_query("""
        SELECT
            product_id,
            product_name,
            category,
            sub_category,
            ROUND(SUM(sales), 2)     AS revenue,
            COUNT(*)                 AS units_sold,
            COUNT(DISTINCT order_id) AS orders,
            RANK() OVER (ORDER BY SUM(sales) DESC) AS rnk
        FROM sales
        GROUP BY product_id, product_name, category, sub_category
        ORDER BY rnk
        LIMIT 10
    """, conn)

    # ── 3d. Month-over-month trends ────────────────────────────────────────────
    results["mom"] = pd.read_sql_query("""
        WITH monthly AS (
            SELECT
                strftime('%Y-%m', order_date) AS year_month,
                strftime('%Y', order_date)    AS year,
                strftime('%m', order_date)    AS month,
                ROUND(SUM(sales), 2)          AS revenue,
                COUNT(DISTINCT order_id)      AS orders,
                COUNT(DISTINCT customer_id)   AS customers
            FROM sales
            GROUP BY year_month
        ),
        with_lag AS (
            SELECT
                year_month, year, month, revenue, orders, customers,
                LAG(revenue) OVER (ORDER BY year_month) AS prev_month_revenue,
                LAG(orders)  OVER (ORDER BY year_month) AS prev_month_orders
            FROM monthly
        )
        SELECT
            year_month,
            year,
            month,
            revenue,
            orders,
            customers,
            prev_month_revenue,
            ROUND(
                (revenue - prev_month_revenue) * 100.0
                / NULLIF(prev_month_revenue, 0), 2
            ) AS mom_revenue_growth_pct,
            ROUND(
                (orders - prev_month_orders) * 100.0
                / NULLIF(prev_month_orders, 0), 2
            ) AS mom_order_growth_pct,
            SUM(revenue) OVER (ORDER BY year_month) AS cumulative_revenue
        FROM with_lag
        ORDER BY year_month
    """, conn)

    # ── 3e. Cohort retention ───────────────────────────────────────────────────
    results["cohort"] = pd.read_sql_query("""
        WITH first_order AS (
            SELECT customer_id,
                   strftime('%Y-%m', MIN(order_date)) AS cohort_month
            FROM sales
            GROUP BY customer_id
        ),
        order_months AS (
            SELECT DISTINCT
                s.customer_id,
                fo.cohort_month,
                strftime('%Y-%m', s.order_date) AS order_month
            FROM sales s
            JOIN first_order fo ON s.customer_id = fo.customer_id
        ),
        periods AS (
            SELECT
                customer_id,
                cohort_month,
                order_month,
                (
                    (CAST(SUBSTR(order_month, 1, 4) AS INTEGER)
                     - CAST(SUBSTR(cohort_month, 1, 4) AS INTEGER)) * 12
                    + CAST(SUBSTR(order_month, 6, 2) AS INTEGER)
                    - CAST(SUBSTR(cohort_month, 6, 2) AS INTEGER)
                ) AS period_number
            FROM order_months
        ),
        cohort_sizes AS (
            SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
            FROM first_order
            GROUP BY cohort_month
        ),
        retained AS (
            SELECT cohort_month, period_number,
                   COUNT(DISTINCT customer_id) AS retained_customers
            FROM periods
            GROUP BY cohort_month, period_number
        )
        SELECT
            r.cohort_month,
            cs.cohort_size,
            r.period_number,
            r.retained_customers,
            ROUND(r.retained_customers * 100.0 / cs.cohort_size, 2) AS retention_rate_pct
        FROM retained r
        JOIN cohort_sizes cs ON r.cohort_month = cs.cohort_month
        WHERE r.period_number <= 12
        ORDER BY r.cohort_month, r.period_number
    """, conn)

    # ── 3f. Customer LTV segmentation ─────────────────────────────────────────
    results["clv"] = pd.read_sql_query("""
        WITH customer_stats AS (
            SELECT
                customer_id,
                customer_name,
                segment,
                region,
                COUNT(DISTINCT order_id) AS order_count,
                COUNT(*)                 AS line_items,
                ROUND(SUM(sales), 2)     AS total_spend,
                ROUND(AVG(sales), 2)     AS avg_line_value,
                MIN(order_date)          AS first_order,
                MAX(order_date)          AS last_order
            FROM sales
            GROUP BY customer_id, customer_name, segment, region
        ),
        clv_scored AS (
            SELECT *,
                CASE
                    WHEN total_spend >= 3000                         THEN 'VIP'
                    WHEN total_spend >= 1000 AND order_count >= 5    THEN 'Loyal'
                    WHEN total_spend >= 500                          THEN 'Growth'
                    ELSE                                                  'New / At-Risk'
                END AS clv_segment
            FROM customer_stats
        )
        SELECT
            clv_segment,
            COUNT(*)                   AS customer_count,
            ROUND(AVG(total_spend), 2) AS avg_spend,
            ROUND(SUM(total_spend), 2) AS segment_revenue,
            ROUND(AVG(order_count), 2) AS avg_orders,
            ROUND(
                SUM(total_spend) * 100.0
                / SUM(SUM(total_spend)) OVER (), 2
            )                          AS revenue_share_pct
        FROM clv_scored
        GROUP BY clv_segment
        ORDER BY avg_spend DESC
    """, conn)

    # ── 3g. Category breakdown ─────────────────────────────────────────────────
    results["category"] = pd.read_sql_query("""
        SELECT
            category,
            sub_category,
            ROUND(SUM(sales), 2)     AS revenue,
            COUNT(DISTINCT order_id) AS orders,
            RANK() OVER (ORDER BY SUM(sales) DESC) AS overall_rank
        FROM sales
        GROUP BY category, sub_category
        ORDER BY revenue DESC
    """, conn)

    # ── 3h. YoY by category ────────────────────────────────────────────────────
    results["yoy"] = pd.read_sql_query("""
        WITH yearly_cat AS (
            SELECT
                strftime('%Y', order_date) AS year,
                category,
                ROUND(SUM(sales), 2)       AS revenue
            FROM sales
            GROUP BY year, category
        )
        SELECT
            category,
            year,
            revenue,
            LAG(revenue) OVER (PARTITION BY category ORDER BY year) AS prev_year_revenue,
            ROUND(
                (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY year))
                * 100.0
                / NULLIF(LAG(revenue) OVER (PARTITION BY category ORDER BY year), 0),
                2
            ) AS yoy_growth_pct
        FROM yearly_cat
        ORDER BY category, year
    """, conn)

    # ── 3i. Segment × Region matrix ───────────────────────────────────────────
    results["seg_region"] = pd.read_sql_query("""
        SELECT
            segment,
            region,
            ROUND(SUM(sales), 2)        AS revenue,
            COUNT(DISTINCT order_id)    AS orders,
            COUNT(DISTINCT customer_id) AS customers,
            RANK() OVER (PARTITION BY segment ORDER BY SUM(sales) DESC) AS rank_in_segment
        FROM sales
        GROUP BY segment, region
        ORDER BY segment, revenue DESC
    """, conn)

    print("   All SQL queries executed successfully.")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — EXPORT OUTPUT FILES
# ══════════════════════════════════════════════════════════════════════════════

def export_outputs(df: pd.DataFrame, results: dict):
    print("[4/5] Exporting output files …")

    # tableau_sales.csv — enriched flat file
    tableau_cols = [
        "order_id", "order_date", "ship_date", "ship_mode", "ship_days",
        "customer_id", "customer_name", "segment",
        "city", "state", "region", "postal_code",
        "product_id", "category", "sub_category", "product_name",
        "sales",
        "order_year", "order_month", "order_month_name",
        "order_quarter", "order_yearmonth",
    ]
    df[tableau_cols].to_csv(OUT_TABLEAU, index=False)
    print(f"   Saved: tableau_sales.csv ({len(df):,} rows)")

    # mom_trends.csv
    results["mom"].to_csv(OUT_MOM, index=False)
    print(f"   Saved: mom_trends.csv ({len(results['mom'])} rows)")

    # regional_rankings.csv
    results["regional"].to_csv(OUT_REGION, index=False)
    print(f"   Saved: regional_rankings.csv ({len(results['regional'])} rows)")

    # cohort_analysis.csv
    results["cohort"].to_csv(OUT_COHORT, index=False)
    print(f"   Saved: cohort_analysis.csv ({len(results['cohort'])} rows)")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — GENERATE SUMMARY REPORT
# ══════════════════════════════════════════════════════════════════════════════

def generate_summary(results: dict):
    print("[5/5] Generating model_summary.txt …")

    s   = results["summary"].iloc[0]
    reg = results["regional"]
    mom = results["mom"].dropna(subset=["mom_revenue_growth_pct"])
    cat = results["category"].groupby("category")["revenue"].sum().sort_values(ascending=False)
    clv = results["clv"]
    cohort_p0 = results["cohort"][results["cohort"]["period_number"] == 0]
    cohort_p1 = results["cohort"][results["cohort"]["period_number"] == 1]
    yoy = results["yoy"].dropna(subset=["yoy_growth_pct"])

    best_region       = reg.iloc[0]["region"]
    best_region_rev   = reg.iloc[0]["revenue"]
    best_region_pct   = reg.iloc[0]["revenue_pct"]
    best_category     = cat.index[0]
    best_category_rev = cat.iloc[0]

    avg_mom_growth    = mom["mom_revenue_growth_pct"].mean()
    best_mom_row      = mom.loc[mom["mom_revenue_growth_pct"].idxmax()]
    worst_mom_row     = mom.loc[mom["mom_revenue_growth_pct"].idxmin()]

    avg_retention_p1  = cohort_p1["retention_rate_pct"].mean() if len(cohort_p1) else 0

    top10 = results["top10_products"]

    # Build lines
    lines = []
    div   = "=" * 65

    lines += [
        div,
        "  SALES BI DASHBOARD — MODEL SUMMARY REPORT",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        div,
        "",
        "── OVERALL METRICS ────────────────────────────────────────",
        f"  Total Revenue          : ${s['total_revenue']:>12,.2f}",
        f"  Total Orders           : {int(s['total_orders']):>12,}",
        f"  Total Customers        : {int(s['total_customers']):>12,}",
        f"  Total Line Items       : {int(s['total_line_items']):>12,}",
        f"  Avg Line Item Value    : ${s['avg_line_value']:>12,.2f}",
        f"  Date Range             : {s['first_order_date']} → {s['last_order_date']}",
        "",
        "── REGIONAL PERFORMANCE ────────────────────────────────────",
    ]

    for _, row in reg.iterrows():
        marker = " ◀ BEST" if row["region"] == best_region else ""
        lines.append(
            f"  #{int(row['revenue_rank'])} {row['region']:<10} "
            f"Rev: ${row['revenue']:>10,.2f}  "
            f"({row['revenue_pct']}%)  "
            f"Orders: {int(row['orders']):>4,}{marker}"
        )

    lines += [
        "",
        "── CATEGORY BREAKDOWN ──────────────────────────────────────",
    ]
    for cname, crev in cat.items():
        marker = " ◀ BEST" if cname == best_category else ""
        pct = round(crev * 100 / s["total_revenue"], 1)
        lines.append(f"  {cname:<20} ${crev:>10,.2f}  ({pct}%){marker}")

    lines += [
        "",
        "── TOP 10 PRODUCTS BY REVENUE ──────────────────────────────",
    ]
    for _, row in top10.iterrows():
        name_trunc = row["product_name"][:45]
        lines.append(
            f"  #{int(row['rnk']):<2} ${row['revenue']:>8,.2f}  "
            f"[{row['sub_category']}]  {name_trunc}"
        )

    lines += [
        "",
        "── MONTH-OVER-MONTH REVENUE TRENDS ─────────────────────────",
        f"  Average MoM Growth     : {avg_mom_growth:+.2f}%",
        f"  Best Month             : {best_mom_row['year_month']}  "
        f"({best_mom_row['mom_revenue_growth_pct']:+.1f}%  Rev: ${best_mom_row['revenue']:,.2f})",
        f"  Worst Month            : {worst_mom_row['year_month']}  "
        f"({worst_mom_row['mom_revenue_growth_pct']:+.1f}%  Rev: ${worst_mom_row['revenue']:,.2f})",
    ]

    # YoY growth last available year per category
    lines += ["", "── YEAR-OVER-YEAR GROWTH BY CATEGORY ───────────────────────"]
    for cname in yoy["category"].unique():
        subset = yoy[yoy["category"] == cname]
        last = subset.iloc[-1]
        lines.append(
            f"  {cname:<20} {last['year']}: {last['yoy_growth_pct']:+.1f}%  "
            f"(from ${last['prev_year_revenue']:,.2f} → ${last['revenue']:,.2f})"
        )

    lines += [
        "",
        "── CUSTOMER LTV SEGMENTATION ───────────────────────────────",
    ]
    for _, row in clv.iterrows():
        lines.append(
            f"  {row['clv_segment']:<16} Customers: {int(row['customer_count']):>4}  "
            f"Avg Spend: ${row['avg_spend']:>8,.2f}  "
            f"Rev Share: {row['revenue_share_pct']}%"
        )

    lines += [
        "",
        "── COHORT RETENTION (Period 1 = 1 Month After Acquisition) ─",
        f"  Avg 1-Month Retention  : {avg_retention_p1:.1f}%",
        f"  Cohorts Analysed       : {cohort_p0['cohort_month'].nunique()}",
    ]

    # Top 3 insights
    insight_region_gap = round(100 - reg.iloc[1]["revenue_pct"] / reg.iloc[0]["revenue_pct"] * 100, 1) if len(reg) > 1 else 0
    lines += [
        "",
        div,
        "  TOP 3 BUSINESS INSIGHTS",
        div,
        "",
        f"  1. {best_region} is the dominant region, accounting for {best_region_pct}% of",
        f"     total revenue (${best_region_rev:,.2f}). The gap to the #2 region",
        f"     represents a meaningful concentration risk.",
        "",
        f"  2. {best_category} drives the largest revenue share ({round(best_category_rev*100/s['total_revenue'],1)}%).",
        f"     The YoY growth trajectory for this category should be",
        f"     a primary focus for inventory and marketing planning.",
        "",
        f"  3. Average MoM revenue growth is {avg_mom_growth:+.2f}%. The business shows",
        f"     clear seasonality — {best_mom_row['year_month']} was the peak month",
        f"     (+{best_mom_row['mom_revenue_growth_pct']:.1f}%). Cohort retention at",
        f"     month 1 averages {avg_retention_p1:.1f}%, indicating room to improve",
        f"     repeat-purchase campaigns.",
        "",
        div,
        "  OUTPUT FILES",
        div,
        "  sales_database.db      — SQLite database (indexed)",
        "  tableau_sales.csv      — Enriched flat file for Tableau",
        "  mom_trends.csv         — Month-over-month revenue data",
        "  regional_rankings.csv  — Regional breakdown with rankings",
        "  cohort_analysis.csv    — Cohort retention matrix",
        "  sales_queries.sql      — All advanced SQL queries",
        div,
    ]

    report = "\n".join(lines)
    with open(OUT_SUMMARY, "w") as f:
        f.write(report)
    print(f"   Saved: model_summary.txt")
    return report


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 65)
    print("  SALES BI DASHBOARD — ANALYSIS PIPELINE")
    print("=" * 65 + "\n")

    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    df      = load_and_clean(CSV_PATH)
    conn    = load_to_sqlite(df, DB_PATH)
    results = run_analyses(conn)
    export_outputs(df, results)
    report  = generate_summary(results)
    conn.close()

    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE")
    print("=" * 65)
    print(report)


if __name__ == "__main__":
    main()
