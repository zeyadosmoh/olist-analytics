-- One row per payment. An order can be split across several payments,
-- so the primary key is (order_id, payment_sequence) -> order_payment_key.
with source as (
    select * from {{ source('raw', 'order_payments') }}
)

select
    order_id || '-' || payment_sequential          as order_payment_key,
    order_id,
    payment_sequential::integer                    as payment_sequence,
    payment_type,
    payment_installments::integer                  as installments,
    payment_value::numeric(12, 2)                  as amount
from source
