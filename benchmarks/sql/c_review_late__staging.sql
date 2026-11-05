-- (c) Average review score: late vs on-time (delivered orders with a review).
-- STAGING: typed views, but the latest-review dedupe and late flag still run here.
with latest_review as (
    select distinct on (order_id)
        order_id,
        score
    from staging.stg_order_reviews
    order by order_id, created_at desc, answered_at desc nulls last
)
select
    case when o.delivered_to_customer_at::date > o.estimated_delivery_at::date
         then 'Late' else 'On time' end   as status,
    avg(r.score)                          as avg_review_score,
    count(*)                              as orders
from staging.stg_orders o
join latest_review r on r.order_id = o.order_id
where o.delivered_to_customer_at is not null
  and o.estimated_delivery_at is not null
  and r.score is not null
group by 1
order by 1;
