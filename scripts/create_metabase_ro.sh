#!/usr/bin/env bash
# Creates/updates the read-only "metabase_ro" Postgres user.
# Reads PG_USER and MB_DB_PASSWORD from .env (never committed).
set -euo pipefail

cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

: "${MB_DB_PASSWORD:?MB_DB_PASSWORD is not set in .env}"

docker exec -i olist_pg psql -U "$PG_USER" -d olist \
  -v mb_password="$MB_DB_PASSWORD" < scripts/create_metabase_ro.sql
