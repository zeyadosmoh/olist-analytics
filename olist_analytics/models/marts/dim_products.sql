-- One row per product, with the English category name.
-- Fallback: Portuguese name if no translation exists, 'unknown' if no category.
with products as (
    select * from {{ ref('stg_products') }}
),

translation as (
    select * from {{ ref('stg_product_category_translation') }}
)

select
    p.product_id,
    coalesce(t.category_name_english, p.category_name, 'unknown')  as category,
    p.category_name                                                as category_name_pt,
    p.name_length,
    p.description_length,
    p.photos_count,
    p.weight_g,
    p.length_cm,
    p.height_cm,
    p.width_cm
from products p
left join translation t on t.category_name = p.category_name
