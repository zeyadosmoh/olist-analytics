-- One row per item sold, enriched with the product category and order context
-- (purchase time, customer, customer state at order time, revenue flag).
-- Lets BI tools slice revenue by category AND state with the same filters.
-- Same revenue rule as fct_orders: price + freight, 0 for canceled/unavailable orders.
with items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select
        order_id,
        customer_unique_id,
        customer_state,
        purchased_at,
        is_revenue_order
    from {{ ref('fct_orders') }}
),

products as (
    select product_id, category from {{ ref('dim_products') }}
)

select
    i.order_item_key,
    i.order_id,
    i.item_number,
    i.product_id,
    coalesce(p.category, 'unknown')                             as category,
    o.customer_unique_id,
    o.customer_state,
    o.purchased_at,
    o.is_revenue_order,
    i.price,
    i.freight_value,
    case when o.is_revenue_order then i.price + i.freight_value else 0 end as revenue
from items i
join orders o        on o.order_id = i.order_id
left join products p on p.product_id = i.product_id
