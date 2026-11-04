-- One row per (review, order). A review_id can cover several orders and an
-- order can have several reviews, so the key is review_id + order_id.
with source as (
    select * from {{ source('raw', 'order_reviews') }}
)

select
    review_id || '-' || order_id                   as review_key,
    review_id,
    order_id,
    review_score::integer                          as score,
    review_comment_title                           as comment_title,
    review_comment_message                         as comment_message,
    review_creation_date::timestamp                as created_at,
    review_answer_timestamp::timestamp             as answered_at
from source
