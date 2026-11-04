{% docs revenue_definition %}
**Revenue** = sum of `price + freight_value` of the order's items,
counting only orders whose status is **not** `canceled` or `unavailable`.

It is based on items, not payments. Total payments are ~1% higher than
items + freight (16.01M vs 15.84M) because:

- ~98% of the gap: 775 orders were paid but have no item rows. Almost all
  are `unavailable` (603) or `canceled` (164): paid, then never fulfilled.
- ~2% of the gap: customers paid slightly more than the items, mostly on
  multi-installment payments (installment interest).
- A tiny negative part: payments slightly below item value (vouchers/rounding).
{% enddocs %}

{% docs order_status %}
Olist order status. One of: `created`, `approved`, `invoiced`, `processing`,
`shipped`, `delivered`, `canceled`, `unavailable`.
{% enddocs %}
