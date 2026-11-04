-- One row per product. Fixes the "lenght" typos from the source and casts
-- dimensions to numbers. Category is in Portuguese (translation is a separate source).
with source as (
    select * from {{ source('raw', 'products') }}
)

select
    product_id,
    product_category_name                          as category_name,
    product_name_lenght::integer                   as name_length,
    product_description_lenght::integer            as description_length,
    product_photos_qty::integer                    as photos_count,
    product_weight_g::numeric                      as weight_g,
    product_length_cm::numeric                     as length_cm,
    product_height_cm::numeric                     as height_cm,
    product_width_cm::numeric                      as width_cm
from source
