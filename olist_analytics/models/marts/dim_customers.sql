-- One row per real customer (customer_unique_id). Olist gives a new
-- customer_id per order, so customer_unique_id is the person-level key.
with orders as (
    select * from {{ ref('fct_orders') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

-- Location from the customer's most recent order.
latest_location as (
    select distinct on (c.customer_unique_id)
        c.customer_unique_id,
        c.state,
        c.city
    from customers c
    join {{ ref('stg_orders') }} o on o.customer_id = c.customer_id
    order by c.customer_unique_id, o.purchased_at desc
),

order_stats as (
    select
        customer_unique_id,
        min(purchased_at)::date   as first_order_date,
        max(purchased_at)::date   as last_order_date,
        count(*)                  as orders_count,
        sum(revenue)              as lifetime_value
    from orders
    group by customer_unique_id
)

select
    s.customer_unique_id,
    l.state,
    l.city,
    s.first_order_date,
    s.last_order_date,
    s.orders_count,
    s.lifetime_value,
    s.orders_count > 1          as is_repeat
from order_stats s
left join latest_location l on l.customer_unique_id = s.customer_unique_id
