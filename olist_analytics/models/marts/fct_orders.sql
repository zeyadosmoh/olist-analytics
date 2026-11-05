-- One row per order: order lifecycle, item/payment totals, delivery KPIs, review.
-- Revenue rule (used by every mart): price + freight of the order's items,
-- only for orders whose status is NOT 'canceled' or 'unavailable'.
with orders as (
    select * from {{ ref('stg_orders') }}
),

customers as (
    select customer_id, customer_unique_id, state from {{ ref('stg_customers') }}
),

items as (
    select
        order_id,
        count(*)            as items_count,
        sum(price)          as items_value,
        sum(freight_value)  as freight_value
    from {{ ref('stg_order_items') }}
    group by order_id
),

payments as (
    select
        order_id,
        sum(amount)         as payment_total
    from {{ ref('stg_order_payments') }}
    group by order_id
),

-- Some orders have several reviews: keep the most recent one.
latest_review as (
    select distinct on (order_id)
        order_id,
        score
    from {{ ref('stg_order_reviews') }}
    order by order_id, created_at desc, answered_at desc nulls last
)

select
    o.order_id,
    c.customer_unique_id,
    c.state                                                     as customer_state,
    o.status,
    o.status not in ('canceled', 'unavailable')                 as is_revenue_order,

    o.purchased_at,
    o.approved_at,
    o.delivered_to_carrier_at,
    o.delivered_to_customer_at,
    o.estimated_delivery_at,

    coalesce(i.items_count, 0)                                  as items_count,
    coalesce(i.items_value, 0)                                  as items_value,
    coalesce(i.freight_value, 0)                                as freight_value,
    case
        when o.status not in ('canceled', 'unavailable')
            then coalesce(i.items_value, 0) + coalesce(i.freight_value, 0)
        else 0
    end                                                         as revenue,
    coalesce(p.payment_total, 0)                                as payment_total,

    -- Calendar days from purchase to delivery; null if not delivered yet.
    o.delivered_to_customer_at::date - o.purchased_at::date     as delivery_days,
    -- Late = delivered on a later day than the estimate; null if not delivered.
    o.delivered_to_customer_at::date > o.estimated_delivery_at::date as is_late,

    r.score                                                     as review_score
from orders o
left join customers c      on c.customer_id = o.customer_id
left join items i          on i.order_id = o.order_id
left join payments p       on p.order_id = o.order_id
left join latest_review r  on r.order_id = o.order_id
