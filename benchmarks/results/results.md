Indexes on marts: marts.fct_order_items_customer_state_purchased_at_order_id_reven_idx1, marts.fct_order_items_purchased_at_category_revenue_idx1

| query | raw ms | staging ms | marts ms | marts+idx ms | raw / marts | raw / marts+idx |
|---|---:|---:|---:|---:|---:|---:|
| a_monthly_trend | 129.56 | 148.61 | 58.84 | 31.68 | 2.2x | 4.1x |
| b_top_categories | 145.18 | 156.47 | 28.89 | 14.88 | 5.0x | 9.8x |
| b_top_categories (marts_monthly) | - | - | 0.33 | 0.32 | 446.7x | 460.9x |
| c_review_late | 539.61 | 569.26 | 40.61 | 36.22 | 13.3x | 14.9x |

| file | mode | median ms | min ms | max ms | planning ms | buffers | JIT ms |
|---|---|---:|---:|---:|---:|---:|---:|
| a_monthly_trend__marts | no_index | 58.84 | 40.18 | 66.68 | 0.14 | 3051 | 0.00 |
| a_monthly_trend__marts | default | 31.68 | 24.43 | 37.09 | 0.14 | 139 | 0.00 |
| a_monthly_trend__raw | default | 129.56 | 121.61 | 186.64 | 0.22 | 6443 | 0.00 |
| a_monthly_trend__staging | default | 148.61 | 144.28 | 159.66 | 0.30 | 6443 | 0.00 |
| b_top_categories__marts | no_index | 28.89 | 24.89 | 31.73 | 0.12 | 3051 | 0.00 |
| b_top_categories__marts | default | 14.88 | 14.65 | 26.78 | 0.12 | 289 | 0.00 |
| b_top_categories__marts_monthly | no_index | 0.33 | 0.30 | 0.53 | 0.09 | 17 | 0.00 |
| b_top_categories__marts_monthly | default | 0.32 | 0.27 | 0.53 | 0.07 | 17 | 0.00 |
| b_top_categories__raw | default | 145.18 | 121.38 | 151.92 | 0.32 | 5737 | 0.00 |
| b_top_categories__staging | default | 156.47 | 132.83 | 181.65 | 0.47 | 5737 | 0.00 |
| c_review_late__marts | no_index | 40.61 | 31.68 | 61.11 | 0.08 | 2432 | 0.00 |
| c_review_late__marts | default | 36.22 | 34.69 | 63.67 | 0.09 | 2432 | 0.00 |
| c_review_late__raw | default | 539.61 | 462.05 | 560.68 | 0.17 | 4640 | 0.00 |
| c_review_late__staging | default | 569.26 | 511.73 | 638.80 | 0.20 | 4640 | 0.00 |
