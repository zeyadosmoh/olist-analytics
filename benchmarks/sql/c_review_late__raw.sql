-- (c) Average review score: late vs on-time (delivered orders with a review).
-- RAW: casts, dedupe to the latest review per order, late flag computed at query time.
with latest_review as (
    select distinct on (order_id)
        order_id,
        review_score::integer   as score
    from raw.order_reviews
    order by order_id,
             review_creation_date::timestamp desc,
             review_answer_timestamp::timestamp desc nulls last
)
select
    case when o.order_delivered_customer_date::timestamp::date
              > o.order_estimated_delivery_date::timestamp::date
         then 'Late' else 'On time' end   as status,
    avg(r.score)                          as avg_review_score,
    count(*)                              as orders
from raw.orders o
join latest_review r on r.order_id = o.order_id
where o.order_delivered_customer_date is not null
  and o.order_estimated_delivery_date is not null
  and r.score is not null
group by 1
order by 1;
