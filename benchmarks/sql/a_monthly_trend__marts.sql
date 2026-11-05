-- (a) Monthly revenue + orders trend, State filter = RJ.
-- MARTS: one pre-joined, typed table (same SQL as the dashboard card).
select
    date_trunc('month', purchased_at)::date   as month,
    sum(revenue)                              as revenue,
    count(distinct order_id)                  as orders
from marts.fct_order_items
where is_revenue_order
  and customer_state = 'RJ'
  and purchased_at >= date '2017-01-01'
  and purchased_at <  date '2018-09-01'
group by 1
order by 1;
