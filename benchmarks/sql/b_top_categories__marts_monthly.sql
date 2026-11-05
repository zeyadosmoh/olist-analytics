-- (b) Top 10 categories by revenue, date range = 2018-01-01 .. 2018-06-30.
-- MARTS (pre-aggregated): fct_revenue_monthly has one row per month x category,
-- so only ~1.3k rows are read. Works only for whole-month date ranges.
select
    category,
    sum(revenue)   as revenue
from marts.fct_revenue_monthly
where month >= date '2018-01-01'
  and month <  date '2018-07-01'
group by 1
order by revenue desc, category
limit 10;
