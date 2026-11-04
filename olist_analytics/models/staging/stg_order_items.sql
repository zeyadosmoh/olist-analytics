-- One row per item in an order. Primary key is (order_id, item_number),
-- exposed as order_item_key so it can be tested as a single column.
with source as (
    select * from {{ source('raw', 'order_items') }}
)

select
    order_id || '-' || order_item_id               as order_item_key,
    order_id,
    order_item_id::integer                         as item_number,
    product_id,
    seller_id,
    shipping_limit_date::timestamp                 as shipping_limit_at,
    price::numeric(12, 2)                          as price,
    freight_value::numeric(12, 2)                  as freight_value
from source
