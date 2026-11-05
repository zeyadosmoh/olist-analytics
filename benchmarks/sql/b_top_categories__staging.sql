-- (b) Top 10 categories by revenue, date range = 2018-01-01 .. 2018-06-30.
-- STAGING: typed views, still 4 joins + category fallback at query time.
select
    coalesce(t.category_name_english, p.category_name, 'unknown')  as category,
    sum(i.price + i.freight_value)                                 as revenue
from staging.stg_order_items i
join staging.stg_orders o        on o.order_id = i.order_id
left join staging.stg_products p on p.product_id = i.product_id
left join staging.stg_product_category_translation t
                                 on t.category_name = p.category_name
where o.status not in ('canceled', 'unavailable')
  and o.purchased_at >= date '2018-01-01'
  and o.purchased_at <  date '2018-07-01'
group by 1
order by revenue desc, category
limit 10;
