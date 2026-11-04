#!/usr/bin/env bash
# Load every CSV in data/raw into schema "raw" as text columns.
set -euo pipefail
source .env
PSQL="docker exec -i olist_pg psql -U $PG_USER -d olist -v ON_ERROR_STOP=1 -q"
$PSQL -c "create schema if not exists raw;"
for f in data/raw/*.csv; do
  file=$(basename "$f")
  name=$(basename "$f" .csv | sed -e 's/^olist_//' -e 's/_dataset$//')
  cols=$(head -1 "$f" | sed -e 's/^\xEF\xBB\xBF//' -e 's/\r$//' -e 's/"//g' \
    | awk -F',' '{for(i=1;i<=NF;i++) printf "%s\"%s\" text", (i>1?", ":""), $i}')
  $PSQL -c "drop table if exists raw.$name; create table raw.$name ($cols);"
  $PSQL -c "\copy raw.$name from '/data/raw/$file' with (format csv, header true)"
  echo "loaded raw.$name"
done
