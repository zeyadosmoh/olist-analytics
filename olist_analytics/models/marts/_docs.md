{% docs revenue_definition %}
**Revenue** = sum of `price + freight_value` of the order's items,
counting only orders whose status is **not** `canceled` or `unavailable`.

It is based on items, not payments. Total payments are ~1% higher than
items + freight (16.01M vs 15.84M) because:

- ~98% of the gap: 775 orders with payment records but no item rows; 3 of
  them were paid R$0.00. Almost all are `unavailable` (603) or `canceled`
  (164; the 3 R$0.00 orders are among these): paid, then never fulfilled.
- ~2% of the gap: customers paid slightly more than the items, mostly on
  multi-installment payments (this fits installment interest;
  the data can't prove the cause).
- A tiny negative part: payments slightly below item value (vouchers/rounding).
{% enddocs %}

{% docs order_status %}
Olist order status. One of: `created`, `approved`, `invoiced`, `processing`,
`shipped`, `delivered`, `canceled`, `unavailable`.
{% enddocs %}

{% docs kpi_reconciliation %}
**Why dashboard KPIs differ from mart row counts** (all data, no filters).

The dashboard KPIs count only orders that **count toward revenue AND have at
least one item row** (they are built on `fct_order_items` where
`is_revenue_order`).

**Orders KPI = 98,199 vs `fct_orders` = 99,441 (diff 1,242)**

| status        | has items | orders | why excluded          |
|---------------|-----------|-------:|-----------------------|
| `canceled`    | yes       |    461 | not a revenue order   |
| `canceled`    | no        |    164 | not a revenue order   |
| `unavailable` | yes       |      6 | not a revenue order   |
| `unavailable` | no        |    603 | not a revenue order   |
| `created`     | no        |      5 | no items, no revenue  |
| `invoiced`    | no        |      2 | no items, no revenue  |
| `shipped`     | no        |      1 | no items, no revenue  |
| **total**     |           |**1,242**|                      |

So 1,234 are canceled/unavailable, and 8 more are valid-status orders that
have no item rows.

**Customers KPI = 94,983 vs `dim_customers` = 96,096 (diff 1,113)**

`dim_customers` has one row per `customer_unique_id` with **any** order.
The KPI only counts customers with at least one order from the KPI set above.
The 1,113 missing customers:

- 1,106 placed only canceled/unavailable orders (669 of them also had no item rows).
- 7 placed only valid-status orders with no item rows.

Check with:
```sql
select status, items_count > 0 as has_items, count(*)
from marts.fct_orders
where not (is_revenue_order and items_count > 0)
group by 1, 2;
```
{% enddocs %}
