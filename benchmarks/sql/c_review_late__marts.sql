-- (c) Average review score: late vs on-time (delivered orders with a review).
-- MARTS: is_late and review_score (latest review) are already columns of fct_orders.
select
    case when is_late then 'Late' else 'On time' end   as status,
    avg(review_score)                                  as avg_review_score,
    count(*)                                           as orders
from marts.fct_orders
where is_late is not null
  and review_score is not null
group by 1
order by 1;
