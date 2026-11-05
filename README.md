# Olist Analytics Stack (PostgreSQL · dbt · Metabase)

## Metabase dashboards

Metabase runs at http://localhost:3000 (`docker compose up -d`). It reads only
the `marts` schema through the read-only `metabase_ro` user
(`scripts/create_metabase_ro.sh`).

The **Sales Overview** dashboard is built from code, so it is reproducible:

```bash
source .venv/bin/activate
python scripts/metabase/build_sales_dashboard.py   # needs MB_API_KEY in .env
```

Re-running updates the existing cards and dashboard in place and then checks
that every card runs, with and without filters.
