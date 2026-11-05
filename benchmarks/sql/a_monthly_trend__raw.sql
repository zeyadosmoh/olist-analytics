-- (a) Monthly revenue + orders trend, State filter = RJ.
-- RAW: text tables, so every column is cast and 3 tables are joined at query time.
select
    date_trunc('month', o.order_purchase_timestamp::timestamp)::date   as month,
    sum(i.price::numeric(12, 2) + i.freight_value::numeric(12, 2))     as revenue,
    count(distinct o.order_id)                                         as orders
from raw.orders o
join raw.customers c   on c.customer_id = o.customer_id
join raw.order_items i on i.order_id = o.order_id
where o.order_status not in ('canceled', 'unavailable')
  and c.customer_state = 'RJ'
  and o.order_purchase_timestamp::timestamp >= date '2017-01-01'
  and o.order_purchase_timestamp::timestamp <  date '2018-09-01'
group by 1
order by 1;
