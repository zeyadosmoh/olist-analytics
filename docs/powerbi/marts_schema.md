# Marts schema reference (for Power BI)

Reference for building the Power BI model on top of the dbt marts.

- **Database:** `olist` on `localhost:5433` (Postgres 16, container `olist_pg`)
- **Schema:** `marts` (all 5 tables are built by dbt as plain tables)
- **Login:** `powerbi_ro`, a read-only role with `SELECT` on `marts` only. It has no access to `raw` or `staging`. The password is `POWERBI_RO_PASSWORD` in `.env`.
- **Connection limit:** `powerbi_ro` has `CONNECTION LIMIT 25` (the server allows 100 in total). Power BI loads tables in parallel and opens extra connections for metadata, so a limit of 10 failed with `53300: too many connections for role "powerbi_ro"`.
- **Snapshot:** row counts below were measured on 2026-11-10. Purchases range from 2016-09-04 to 2018-10-17.

Postgres does not enforce primary or foreign keys on these tables (dbt builds them with `CREATE TABLE AS`, so every column shows as nullable). dbt tests check the keys instead (`unique`, `not_null`, `relationships` in `olist_analytics/models/marts/_marts.yml`). The checks below were also run against the data.

## Overview

| Table | Rows | Grain (one row = ...) | Primary key |
|---|---:|---|---|
| `fct_orders` | 99,441 | one order | `order_id` |
| `fct_order_items` | 112,650 | one item line inside an order | `order_item_key` (= `order_id` + `item_number`) |
| `dim_customers` | 96,096 | one real customer (person) | `customer_unique_id` |
| `dim_products` | 32,951 | one product | `product_id` |
| `fct_revenue_monthly` | 1,282 | one (purchase month, product category) pair | `month_category_key` (= `month` + `category`) |

## Revenue rule (same in every mart)

Revenue = item `price` + `freight_value`. It counts only orders whose `status` is **not** `canceled` or `unavailable`. The flag `is_revenue_order` marks the orders that count.

---

## fct_orders

**Grain:** one row per order. **Rows:** 99,441. **PK:** `order_id`. Checked: 99,441 distinct values, 0 nulls.

| # | Column | Type | Notes |
|---:|---|---|---|
| 1 | `order_id` | text | Primary key |
| 2 | `customer_unique_id` | text | FK to `dim_customers` |
| 3 | `customer_state` | text | Customer's state (UF) at the time of this order |
| 4 | `status` | text | created, approved, invoiced, processing, shipped, delivered, canceled, unavailable |
| 5 | `is_revenue_order` | boolean | True if status is not canceled/unavailable |
| 6 | `purchased_at` | timestamp | When the order was placed |
| 7 | `approved_at` | timestamp | Payment approved |
| 8 | `delivered_to_carrier_at` | timestamp | Handed to the carrier |
| 9 | `delivered_to_customer_at` | timestamp | Delivered (null if not delivered) |
| 10 | `estimated_delivery_at` | timestamp | Promised delivery date |
| 11 | `items_count` | bigint | Items in the order (0 if none recorded) |
| 12 | `items_value` | numeric | Sum of item prices |
| 13 | `freight_value` | numeric | Sum of item freight |
| 14 | `revenue` | numeric | Revenue rule, 0 for canceled/unavailable |
| 15 | `payment_total` | numeric | Sum of payments (can differ from revenue) |
| 16 | `delivery_days` | integer | Calendar days purchase to delivery (null if not delivered) |
| 17 | `is_late` | boolean | Delivered on a later day than the estimate (null if not delivered) |
| 18 | `review_score` | integer | 1-5, latest review (null if no review) |

Note: 775 orders have no item rows. They exist here with `items_count = 0` but do not appear in `fct_order_items`.

## fct_order_items

**Grain:** one row per item line in an order. An order with 3 items has 3 rows. **Rows:** 112,650. **PK:** `order_item_key`. Checked: 112,650 distinct values, 0 nulls. `(order_id, item_number)` is also unique.

| # | Column | Type | Notes |
|---:|---|---|---|
| 1 | `order_item_key` | text | Primary key, `order_id` + '-' + `item_number` |
| 2 | `order_id` | text | FK to `fct_orders` |
| 3 | `item_number` | integer | Position of the item in the order (1, 2, ...) |
| 4 | `product_id` | text | FK to `dim_products` |
| 5 | `category` | text | English category, copied from `dim_products` ('unknown' if missing) |
| 6 | `customer_unique_id` | text | FK to `dim_customers`, copied from the order |
| 7 | `customer_state` | text | Customer state at order time, copied from the order |
| 8 | `purchased_at` | timestamp | Order purchase time, copied from the order |
| 9 | `is_revenue_order` | boolean | Copied from the order |
| 10 | `price` | numeric | Item price |
| 11 | `freight_value` | numeric | Item freight |
| 12 | `revenue` | numeric | `price + freight_value`, 0 for canceled/unavailable |

## dim_customers

**Grain:** one row per real customer (person). Olist issues a new `customer_id` for every order. `customer_unique_id` is the person-level key, and `customer_id` is not in the marts. **Rows:** 96,096. **PK:** `customer_unique_id`. Checked: 96,096 distinct values, 0 nulls.

| # | Column | Type | Notes |
|---:|---|---|---|
| 1 | `customer_unique_id` | text | Primary key |
| 2 | `state` | text | State from the customer's most recent order |
| 3 | `city` | text | City from the customer's most recent order |
| 4 | `first_order_date` | date | First order date |
| 5 | `last_order_date` | date | Most recent order date |
| 6 | `orders_count` | bigint | Orders placed (all statuses) |
| 7 | `lifetime_value` | numeric | Total revenue (revenue rule) |
| 8 | `is_repeat` | boolean | More than one order |

## dim_products

**Grain:** one row per product. **Rows:** 32,951. **PK:** `product_id`. Checked: 32,951 distinct values, 0 nulls.

| # | Column | Type | Notes |
|---:|---|---|---|
| 1 | `product_id` | text | Primary key |
| 2 | `category` | text | English category name. Falls back to the Portuguese name, then 'unknown' (610 products). 74 distinct values. |
| 3 | `category_name_pt` | text | Original Portuguese category name |
| 4 | `name_length` | integer | Characters in the product name |
| 5 | `description_length` | integer | Characters in the description |
| 6 | `photos_count` | integer | Number of product photos |
| 7 | `weight_g` | numeric | Weight in grams |
| 8 | `length_cm` | numeric | Length in cm |
| 9 | `height_cm` | numeric | Height in cm |
| 10 | `width_cm` | numeric | Width in cm |

## fct_revenue_monthly

**Grain:** one row per (purchase month, product category). Only revenue orders are counted. **Rows:** 1,282. Months run from 2016-09-01 to 2018-09-01. **PK:** `month_category_key`. Checked: 1,282 distinct values, 0 nulls. `(month, category)` is also unique.

| # | Column | Type | Notes |
|---:|---|---|---|
| 1 | `month_category_key` | text | Primary key, `month` + '\|' + `category` |
| 2 | `month` | date | First day of the purchase month |
| 3 | `category` | text | English product category |
| 4 | `orders` | bigint | Distinct orders with an item in this category and month |
| 5 | `items` | bigint | Items sold |
| 6 | `revenue` | numeric | Price + freight of those items |

This table is a pre-aggregated summary. It can be rebuilt from `fct_order_items`, so don't add it to totals that also use the item-level facts, or revenue will be counted twice.

---

## Keys and relationships

| From (many side) | To (one side) | Cardinality | Checked |
|---|---|---|---|
| `fct_order_items.order_id` | `fct_orders.order_id` | many-to-one | 0 orphans, 0 nulls |
| `fct_order_items.product_id` | `dim_products.product_id` | many-to-one | 0 orphans, 0 nulls |
| `fct_order_items.customer_unique_id` | `dim_customers.customer_unique_id` | many-to-one | 0 orphans, 0 nulls |
| `fct_orders.customer_unique_id` | `dim_customers.customer_unique_id` | many-to-one | 0 orphans, 0 nulls |
| `fct_revenue_monthly.category` | `dim_products.category` | **many-to-many** | every category exists in `dim_products` |

```
dim_customers (customer_unique_id)
   ^ 1                    ^ 1
   | *                    | *
fct_orders (order_id) <-1--*- fct_order_items -*--1-> dim_products (product_id)

fct_revenue_monthly  (stand-alone summary; month + category)
```

### Notes for the Power BI model

- **Star shape:** `fct_order_items` sits in the center, with `dim_products` and `dim_customers` around it. `fct_orders` also links to `dim_customers`.
- **The `fct_orders` <-> `fct_order_items` link is fact-to-fact.** Order-level measures (delivery days, review score, payment total) come from `fct_orders`. Item and category measures come from `fct_order_items`. To avoid ambiguous filter paths, keep only one active path from `dim_customers` to `fct_order_items`, either directly or through `fct_orders`, and make the other relationship inactive.
- **`category` is not unique in `dim_products`,** so a relationship from `fct_revenue_monthly` would be many-to-many. Either leave `fct_revenue_monthly` unrelated, or build a small category dimension (distinct `category`) and relate both tables to it.
- **Dates:** there is no date dimension in the marts. Create a calendar table in Power BI covering 2016-09-01 to 2018-10-31. Relate it to `purchased_at` (convert it to a date) and to `fct_revenue_monthly.month`.
- **States and categories are copied onto `fct_order_items`** (`customer_state`, `category`, `purchased_at`) on purpose. Slicers can filter it without a join, which mirrors how the Metabase dashboard queries it.
- **Two kinds of customer state:** `fct_orders.customer_state` and `fct_order_items.customer_state` are the state *at order time*. `dim_customers.state` is the state from the customer's *most recent* order. For the same customer they can differ.
