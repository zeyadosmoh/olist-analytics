-- One row per order. Casts lifecycle timestamps and shortens column names.
with source as (
    select * from {{ source('raw', 'orders') }}
)

select
    order_id,
    customer_id,
    order_status                                   as status,
    order_purchase_timestamp::timestamp            as purchased_at,
    order_approved_at::timestamp                   as approved_at,
    order_delivered_carrier_date::timestamp        as delivered_to_carrier_at,
    order_delivered_customer_date::timestamp       as delivered_to_customer_at,
    order_estimated_delivery_date::timestamp       as estimated_delivery_at
from source
