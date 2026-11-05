-- One row per item sold, enriched with the product category and order context
-- (purchase time, customer, customer state at order time, revenue flag).
-- Lets BI tools slice revenue by category AND state with the same filters.
-- Same revenue rule as fct_orders: price + freight, 0 for canceled/unavailable orders.
--
-- Indexes (kept only because benchmarks/ showed a real gain, see docs/performance.md):
-- covering, partial indexes for the dashboard's State and Date filters. They hold
-- every column those queries need, so Postgres answers from the index alone
-- (index-only scan) instead of reading the whole table.
-- * Unnamed on purpose: during a rebuild the old table still exists with its
--   indexes, so a fixed name would clash. Postgres picks a free name.
-- * VACUUM ANALYZE marks the new table's pages as all-visible, which index-only
--   scans need. VACUUM cannot run inside a transaction, hence transaction=false.
{{ config(
    post_hook=[
        "create index on {{ this }} (customer_state, purchased_at) include (order_id, revenue) where is_revenue_order",
        "create index on {{ this }} (purchased_at) include (category, revenue) where is_revenue_order",
        {"sql": "vacuum analyze {{ this }}", "transaction": false},
    ]
) }}

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
