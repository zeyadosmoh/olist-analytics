-- One row per (purchase month, product category) with orders, items and revenue.
-- Same revenue rule as fct_orders: price + freight, excluding canceled/unavailable orders.
with items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select order_id, purchased_at from {{ ref('fct_orders') }}
    where is_revenue_order
),

products as (
    select product_id, category from {{ ref('dim_products') }}
)

select
    date_trunc('month', o.purchased_at)::date || '|' || p.category  as month_category_key,
    date_trunc('month', o.purchased_at)::date                       as month,
    p.category,
    count(distinct i.order_id)                                      as orders,
    count(*)                                                        as items,
    sum(i.price + i.freight_value)                                  as revenue
from items i
join orders o   on o.order_id = i.order_id
join products p on p.product_id = i.product_id
group by 1, 2, 3
