# olist_analytics (dbt)

dbt project that transforms the raw Olist tables (schema `raw`) into clean models.

## Run

From the repo root:

```bash
source .venv/bin/activate
set -a && source .env && set +a   # exports PG_USER / PG_PASSWORD
cd olist_analytics
dbt debug    # check the connection
dbt run      # build models
dbt test     # run data tests
```

`profiles.yml` lives in this folder and reads credentials from env vars,
so no secrets are stored in the repo.

## Layers

- `models/staging/` — one view per raw table: types cast, columns renamed.
  Built in schema `analytics_staging`.
