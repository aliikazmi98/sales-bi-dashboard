-- ============================================================
-- Sales BI Dashboard — Advanced SQL Queries
-- Database: SQLite (sales_database.db)
-- Dataset: Superstore Retail Sales
-- ============================================================


-- ============================================================
-- 1. SCHEMA OVERVIEW
-- ============================================================

-- Main fact table (all columns loaded from CSV)
-- SELECT * FROM sales LIMIT 5;


-- ============================================================
-- 2. TOTAL SUMMARY METRICS
-- ============================================================

SELECT
    COUNT(DISTINCT order_id)    AS total_orders,
    COUNT(DISTINCT customer_id) AS total_customers,
    COUNT(*)                    AS total_line_items,
    ROUND(SUM(sales), 2)        AS total_revenue,
    ROUND(AVG(sales), 2)        AS avg_order_line_value,
    MIN(order_date)             AS first_order_date,
    MAX(order_date)             AS last_order_date
FROM sales;


-- ============================================================
-- 3. REGIONAL REVENUE RANKINGS (Window Function)
-- ============================================================

WITH region_metrics AS (
    SELECT
        region,
        COUNT(DISTINCT order_id)    AS orders,
        COUNT(DISTINCT customer_id) AS customers,
        ROUND(SUM(sales), 2)        AS revenue,
        ROUND(AVG(sales), 2)        AS avg_sale
    FROM sales
    GROUP BY region
),
ranked AS (
    SELECT
        region,
        orders,
        customers,
        revenue,
        avg_sale,
        RANK() OVER (ORDER BY revenue DESC)                          AS revenue_rank,
        ROUND(revenue * 100.0 / SUM(revenue) OVER (), 2)            AS revenue_pct,
        ROUND(
            (revenue - LAG(revenue) OVER (ORDER BY revenue DESC))
            * 100.0 / LAG(revenue) OVER (ORDER BY revenue DESC), 2) AS gap_vs_next_pct
    FROM region_metrics
)
SELECT * FROM ranked ORDER BY revenue_rank;


-- ============================================================
-- 4. TOP 10 PRODUCTS BY REVENUE
-- ============================================================

WITH product_revenue AS (
    SELECT
        product_id,
        product_name,
        category,
        sub_category,
        ROUND(SUM(sales), 2)        AS revenue,
        COUNT(*)                    AS units_sold,
        COUNT(DISTINCT order_id)    AS orders,
        ROUND(AVG(sales), 2)        AS avg_sale_per_line,
        RANK() OVER (ORDER BY SUM(sales) DESC) AS rnk
    FROM sales
    GROUP BY product_id, product_name, category, sub_category
)
SELECT *
FROM product_revenue
WHERE rnk <= 10
ORDER BY rnk;


-- ============================================================
-- 5. MONTH-OVER-MONTH REVENUE TRENDS (Window Function + CTE)
-- ============================================================

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
        year_month,
        year,
        month,
        revenue,
        orders,
        customers,
        LAG(revenue) OVER (ORDER BY year_month)   AS prev_month_revenue,
        LAG(orders)  OVER (ORDER BY year_month)   AS prev_month_orders
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
        (revenue - prev_month_revenue) * 100.0 / NULLIF(prev_month_revenue, 0),
        2
    ) AS mom_revenue_growth_pct,
    ROUND(
        (orders - prev_month_orders) * 100.0 / NULLIF(prev_month_orders, 0),
        2
    ) AS mom_order_growth_pct,
    SUM(revenue) OVER (ORDER BY year_month)  AS cumulative_revenue
FROM with_lag
ORDER BY year_month;


-- ============================================================
-- 6. CATEGORY & SUB-CATEGORY BREAKDOWN (JOIN-style CTE)
-- ============================================================

WITH category_totals AS (
    SELECT
        category,
        ROUND(SUM(sales), 2) AS cat_revenue
    FROM sales
    GROUP BY category
),
sub_category_detail AS (
    SELECT
        s.category,
        s.sub_category,
        ROUND(SUM(s.sales), 2)          AS sub_revenue,
        COUNT(DISTINCT s.order_id)       AS orders,
        RANK() OVER (
            PARTITION BY s.category
            ORDER BY SUM(s.sales) DESC
        ) AS rank_within_category
    FROM sales s
    GROUP BY s.category, s.sub_category
)
SELECT
    sc.category,
    ct.cat_revenue,
    sc.sub_category,
    sc.sub_revenue,
    sc.orders,
    sc.rank_within_category,
    ROUND(sc.sub_revenue * 100.0 / ct.cat_revenue, 2) AS pct_of_category
FROM sub_category_detail sc
JOIN category_totals ct ON sc.category = ct.category
ORDER BY sc.category, sc.rank_within_category;


-- ============================================================
-- 7. CUSTOMER LIFETIME VALUE SEGMENTATION
-- ============================================================

WITH customer_stats AS (
    SELECT
        customer_id,
        customer_name,
        segment,
        region,
        COUNT(DISTINCT order_id)    AS order_count,
        COUNT(*)                    AS line_items,
        ROUND(SUM(sales), 2)        AS total_spend,
        ROUND(AVG(sales), 2)        AS avg_line_value,
        MIN(order_date)             AS first_order,
        MAX(order_date)             AS last_order
    FROM sales
    GROUP BY customer_id, customer_name, segment, region
),
clv_scored AS (
    SELECT *,
        NTILE(4) OVER (ORDER BY total_spend DESC) AS spend_quartile,
        NTILE(4) OVER (ORDER BY order_count DESC) AS frequency_quartile,
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
    COUNT(*)                        AS customer_count,
    ROUND(AVG(total_spend), 2)      AS avg_spend,
    ROUND(SUM(total_spend), 2)      AS segment_revenue,
    ROUND(AVG(order_count), 2)      AS avg_orders,
    ROUND(
        SUM(total_spend) * 100.0
        / SUM(SUM(total_spend)) OVER (), 2
    )                               AS revenue_share_pct
FROM clv_scored
GROUP BY clv_segment
ORDER BY avg_spend DESC;


-- ============================================================
-- 8. COHORT RETENTION ANALYSIS
-- ============================================================

WITH first_order AS (
    -- Identify each customer's cohort (first purchase month)
    SELECT
        customer_id,
        strftime('%Y-%m', MIN(order_date)) AS cohort_month
    FROM sales
    GROUP BY customer_id
),
order_months AS (
    -- All months each customer placed an order
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
        -- Compute period index (0 = cohort month, 1 = next month, ...)
        (
            (CAST(SUBSTR(order_month, 1, 4) AS INTEGER) - CAST(SUBSTR(cohort_month, 1, 4) AS INTEGER)) * 12
            + CAST(SUBSTR(order_month, 6, 2) AS INTEGER) - CAST(SUBSTR(cohort_month, 6, 2) AS INTEGER)
        ) AS period_number
    FROM order_months
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM first_order
    GROUP BY cohort_month
),
retained AS (
    SELECT
        p.cohort_month,
        p.period_number,
        COUNT(DISTINCT p.customer_id) AS retained_customers
    FROM periods p
    GROUP BY p.cohort_month, p.period_number
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
ORDER BY r.cohort_month, r.period_number;


-- ============================================================
-- 9. SEGMENT × REGION REVENUE MATRIX (JOIN across dimensions)
-- ============================================================

WITH seg_region AS (
    SELECT
        segment,
        region,
        ROUND(SUM(sales), 2)        AS revenue,
        COUNT(DISTINCT order_id)    AS orders,
        COUNT(DISTINCT customer_id) AS customers
    FROM sales
    GROUP BY segment, region
)
SELECT
    segment,
    region,
    revenue,
    orders,
    customers,
    RANK() OVER (PARTITION BY segment ORDER BY revenue DESC) AS rank_in_segment,
    RANK() OVER (PARTITION BY region  ORDER BY revenue DESC) AS rank_in_region,
    ROUND(revenue * 100.0 / SUM(revenue) OVER (PARTITION BY segment), 2) AS pct_of_segment,
    ROUND(revenue * 100.0 / SUM(revenue) OVER (PARTITION BY region),  2) AS pct_of_region
FROM seg_region
ORDER BY segment, revenue DESC;


-- ============================================================
-- 10. SHIP MODE PERFORMANCE ANALYSIS
-- ============================================================

WITH ship_stats AS (
    SELECT
        ship_mode,
        COUNT(DISTINCT order_id)    AS orders,
        ROUND(SUM(sales), 2)        AS revenue,
        ROUND(AVG(sales), 2)        AS avg_sale,
        -- Average shipping lag in days (SQLite date math)
        ROUND(AVG(
            julianday(ship_date) - julianday(order_date)
        ), 2) AS avg_ship_days
    FROM sales
    GROUP BY ship_mode
)
SELECT *,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    ROUND(revenue * 100.0 / SUM(revenue) OVER (), 2) AS revenue_pct
FROM ship_stats
ORDER BY revenue DESC;


-- ============================================================
-- 11. YEAR-OVER-YEAR COMPARISON BY CATEGORY
-- ============================================================

WITH yearly_cat AS (
    SELECT
        strftime('%Y', order_date) AS year,
        category,
        ROUND(SUM(sales), 2)       AS revenue,
        COUNT(DISTINCT order_id)   AS orders
    FROM sales
    GROUP BY year, category
)
SELECT
    category,
    year,
    revenue,
    orders,
    LAG(revenue) OVER (PARTITION BY category ORDER BY year) AS prev_year_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (PARTITION BY category ORDER BY year))
        * 100.0
        / NULLIF(LAG(revenue) OVER (PARTITION BY category ORDER BY year), 0),
        2
    ) AS yoy_growth_pct
FROM yearly_cat
ORDER BY category, year;
