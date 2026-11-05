-- (a) Monthly revenue + orders trend, State filter = RJ.
-- STAGING: typed views, but still 3 joins (and the casts run inside the views).
select
    date_trunc('month', o.purchased_at)::date   as month,
    sum(i.price + i.freight_value)              as revenue,
    count(distinct o.order_id)                  as orders
from staging.stg_orders o
join staging.stg_customers c   on c.customer_id = o.customer_id
join staging.stg_order_items i on i.order_id = o.order_id
where o.status not in ('canceled', 'unavailable')
  and c.state = 'RJ'
  and o.purchased_at >= date '2017-01-01'
  and o.purchased_at <  date '2018-09-01'
group by 1
order by 1;
