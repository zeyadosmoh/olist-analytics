# olist_analytics (dbt)

dbt project that transforms the raw Olist tables (schema `raw`) into clean models.

## Run

From the repo root:

```bash
source .venv/bin/activate
set -a && source .env && set +a   # exports PG_USER / PG_PASSWORD
cd olist_analytics
dbt debug    # check the connection
dbt build            # build models and run tests, in dependency order
dbt docs generate    # build the docs site
dbt docs serve       # open it in the browser
```

`profiles.yml` lives in this folder and reads credentials from env vars,
so no secrets are stored in the repo.

## Layers

- `models/staging/` — one view per raw table: types cast, columns renamed.
  Built in schema `staging`.
- `models/marts/` — business-ready tables in schema `marts`:
  - `fct_orders` — one row per order: totals, payments, delivery KPIs, review.
  - `dim_customers` — one row per real customer (`customer_unique_id`).
  - `dim_products` — products with English category names.
  - `fct_revenue_monthly` — month x category: orders, items, revenue.

Schema names are used as-is (see `macros/generate_schema_name.sql`).

## Revenue definition

Revenue = `price + freight_value` of items, excluding orders with status
`canceled` or `unavailable`. It is ~1% lower than total payments, mainly
because some unavailable/canceled orders were paid but have no items.
Full explanation in `models/marts/_docs.md`.
