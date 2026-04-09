# Sales BI Dashboard | SQL, Tableau, Excel

End-to-end Sales Business Intelligence project analyzing 9,994 
real retail records using advanced SQL, Python, and Tableau to 
surface actionable revenue insights for executive stakeholders.

## Key Results
- **Total Dataset:** 9,994 sales records across 4 regions
- **Cohort Retention:** 16.0% avg 1-month retention across 43 cohorts
- **Top Region:** West drives 31.4% of total revenue
- **Fastest Growing:** Technology category +21.4% YoY in 2018
- **At-Risk Customers:** 1,282 customers averaging $172 spend identified
  for re-engagement

## Top 3 Business Insights
1. **West region concentration risk** — West accounts for 31.4% of 
   total revenue, nearly double the South (17.2%). Revenue is 
   geographically lopsided.
2. **Technology is growing fastest** — +21.4% YoY in 2018, already 
   the largest category. Office Supplies showed biggest YoY jump 
   (+31.8%), signalling emerging demand.
3. **Low retention, high growth potential** — Only 16% of customers 
   return within 1 month of first purchase. 1,282 "New/At-Risk" 
   customers spending $172 on average represent a major re-engagement 
   opportunity.

## Advanced SQL Techniques Used
- JOINs across product, customer, and region tables
- CTEs for complex multi-step calculations
- Window functions for MoM revenue trends
- Cohort retention analysis across 43 cohorts
- Regional revenue rankings
- Customer lifetime value segmentation
- Top 10 products by revenue

## Project Structure
- `sales_analysis.py` — Main Python + SQL pipeline
- `sales_queries.sql` — All advanced SQL queries
- `sales_database.db` — SQLite database
- `tableau_sales.csv` — Optimized Tableau export
- `mom_trends.csv` — Month-over-month revenue data
- `regional_rankings.csv` — Regional breakdown
- `cohort_analysis.csv` — Retention cohort data
- `model_summary.txt` — Key findings and insights
- `train.csv` — Raw dataset

## Tech Stack
Python, Pandas, SQLite, SQL, Tableau, Excel

## How to Run
pip install pandas

python3 sales_analysis.py

## Resume Bullets
- Transformed 9,994 sales records via advanced SQL (JOINs, CTEs, 
  window functions) in SQLite; surfaced MoM revenue trends, 16% 
  cohort retention across 43 cohorts, and regional rankings showing 
  West region drives 31.4% of total revenue.

- Identified Technology category growing at +21.4% YoY and 1,282 
  at-risk customers averaging $172 spend; built Tableau executive 
  dashboard with drill-down filters enabling targeted re-engagement 
  strategy.

## Dataset
Real retail sales data via Kaggle 
(rohitsahoo/sales-forecasting)

## Dashboard Preview
![Sales Executive Dashboard](dashboard_preview.png)
