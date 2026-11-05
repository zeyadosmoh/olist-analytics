-- (b) Top 10 categories by revenue, date range = 2018-01-01 .. 2018-06-30.
-- MARTS: item-level fact with category and revenue already on each row
-- (same table the dashboard card uses, so any date range works).
select
    category,
    sum(revenue)   as revenue
from marts.fct_order_items
where is_revenue_order
  and purchased_at >= date '2018-01-01'
  and purchased_at <  date '2018-07-01'
group by 1
order by revenue desc, category
limit 10;
