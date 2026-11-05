-- (b) Top 10 categories by revenue, date range = 2018-01-01 .. 2018-06-30.
-- RAW: casts + 4 joins (orders, items, products, translation) + category fallback.
select
    coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category,
    sum(i.price::numeric(12, 2) + i.freight_value::numeric(12, 2))                as revenue
from raw.order_items i
join raw.orders o        on o.order_id = i.order_id
left join raw.products p on p.product_id = i.product_id
left join raw.product_category_name_translation t
                         on t.product_category_name = p.product_category_name
where o.order_status not in ('canceled', 'unavailable')
  and o.order_purchase_timestamp::timestamp >= date '2018-01-01'
  and o.order_purchase_timestamp::timestamp <  date '2018-07-01'
group by 1
order by revenue desc, category
limit 10;
