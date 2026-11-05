# Dashboard query performance: raw vs staging vs marts

**Short version.** For three typical dashboard queries, the dbt **marts** are
**2x to 13x faster** than the same logic written on the **raw** text tables,
and **4x to 15x faster** once two covering indexes are added. The indexes
roughly halve the time of the two filtered queries. The pre-aggregated
`fct_revenue_monthly` table is **about 450x faster**. **Staging views are not faster than raw**: they run
the same plan. Every version of each query returns **exactly** the same rows.

All absolute times here are small (tens to hundreds of milliseconds), because
the dataset is small. See [Honest notes](#honest-notes-read-before-quoting-numbers).

## The three queries

| id | dashboard question | filter used | marts table |
|---|---|---|---|
| (a) | Monthly revenue + orders trend (2017-01 .. 2018-08) | State = `RJ` | `fct_order_items` |
| (b) | Top 10 categories by revenue | Purchase date 2018-01-01 .. 2018-06-30 | `fct_order_items` (+ `fct_revenue_monthly` variant) |
| (c) | Average review score, late vs on-time | none (delivered orders with a review) | `fct_orders` |

Each query is written 3 ways, with the **same business rules** as the dbt models:

- **raw**: `raw.*` tables (all columns are text), so every query casts types
  and joins 3 to 5 tables at query time.
- **staging**: the `staging.*` views (typed, renamed), still joined at query time.
- **marts**: the `marts.*` tables the dashboard uses.

The rules repeated in the raw/staging versions: revenue = item price + freight;
canceled/unavailable orders don't count; state = the customer's state at order
time; category = English name, else Portuguese name, else `unknown`; review =
latest review per order; late = delivered on a later *day* than the estimate.

Why `RJ` and not `SP`: SP is 42% of all items. A filter that keeps almost half
the table can't show what an index does. RJ (13%) is a typical "one state"
filter. (A spot check on SP is in the index section.)

SQL files: [`benchmarks/sql/`](../benchmarks/sql/), named `<query>__<layer>.sql`.

## Method

- **Machine:** Postgres 16.15 in the project's Docker container, on a laptop
  (WSL2, 8 vCPUs, 7 GB RAM). Default Postgres settings: `shared_buffers` 128MB,
  `work_mem` 4MB, JIT on, up to 2 parallel workers per query.
- **Nothing else running:** the Metabase container was stopped during the runs.
- **Fresh statistics:** the runner runs `ANALYZE` on every table it reads first.
- **Measurement:** `EXPLAIN (ANALYZE, BUFFERS)`, keeping the server-side
  **Execution Time**. That leaves out network and client time.
  For each query, 1 warm-up run, then 5 measured runs, and the table shows the **median**.
  The runs take turns across queries (run 1 of every query, then run 2, and so
  on), so a noisy moment on the machine spreads over every query instead of
  hurting one. All data was in memory (warm cache).
- **Marts without vs with indexes, in one run:** each marts query runs twice.
  Once with `enable_indexscan`, `enable_bitmapscan` and `enable_indexonlyscan`
  turned off for that session (the plan Postgres would pick if the indexes didn't
  exist), and once with normal settings. Raw and staging have no indexes.
- **Correctness (diff check):** the runner saves every version's result to
  `benchmarks/results/<file>.csv` and checks it is **byte-identical** to the raw
  version. It refuses to time anything if one differs. You can also check by hand:

  ```bash
  diff benchmarks/results/c_review_late__raw.csv benchmarks/results/c_review_late__marts.csv
  ```

  Result of the final run: all 7 comparisons `IDENTICAL` (20, 10 and 2 rows).

## Dataset size

| table | rows | size on disk |
|---|---:|---:|
| raw.orders | 99,441 | 20 MB |
| raw.customers | 99,441 | 12 MB |
| raw.order_items | 112,650 | 18 MB |
| raw.order_reviews | 99,224 | 17 MB |
| raw.products | 32,951 | 3.3 MB |
| raw.product_category_name_translation | 71 | 8 kB |
| marts.fct_orders | 99,441 | 19 MB |
| marts.fct_order_items | 112,650 | 24 MB |
| marts.fct_revenue_monthly | 1,282 | 136 kB |

## Results

Median execution time in ms (final run, 1 warm-up + 5 runs). Speed-up = raw time / marts time.

| query | raw | staging | marts | marts + indexes | speed-up marts | speed-up marts + idx |
|---|---:|---:|---:|---:|---:|---:|
| (a) monthly trend, State = RJ | 129.6 | 148.6 | 58.8 | 31.7 | 2.2x | 4.1x |
| (b) top 10 categories, date range | 145.2 | 156.5 | 28.9 | 14.9 | 5.0x | 9.8x |
| (b) same, on `fct_revenue_monthly` | 145.2 | 156.5 | 0.33 | 0.32 | 447x | 461x |
| (c) review score, late vs on-time | 539.6 | 569.3 | 40.6 | 36.2 | 13.3x | 14.9x\* |

\* (c) uses no index; marts and marts + indexes run the **same plan**, so the
gap between 40.6 and 36.2 is noise (see below).

Pages read (8 kB blocks, all from memory). Unlike milliseconds, this number is
the same on every run, so it is the most reliable signal:

| query | raw | staging | marts | marts + indexes |
|---|---:|---:|---:|---:|
| (a) | 6,443 | 6,443 | 3,051 | **139** |
| (b) | 5,737 | 5,737 | 3,051 | **289** |
| (b) monthly | | | 17 | 17 |
| (c) | 4,640 | 4,640 | 2,432 | 2,432 |

Full numbers (min / max / planning time / JIT): [`benchmarks/results/results.md`](../benchmarks/results/results.md).
Planning time was under 0.5 ms everywhere, and JIT never kicked in.

## Why marts are faster

1. **Pre-joined.** The raw/staging versions of (a) join orders + customers +
   items and (b) joins orders + items + products + translations, on every
   dashboard load. In marts, dbt did those joins once, at build time: each
   `fct_order_items` row already carries `customer_state`, `purchased_at`,
   `category` and `revenue`. The query reads **one** table, so it reads about
   half the pages (3,051 vs 6,443) and does no hash joins.
2. **Typed.** Raw columns are text, so every row pays for
   `order_purchase_timestamp::timestamp`, `price::numeric(12,2)` and so on,
   before the filter can even run. Marts store real `timestamp` / `numeric` /
   `boolean` columns, so filtering is a plain comparison.
3. **Pre-computed / pre-aggregated.** This is the biggest win:
   - (c) on raw must **sort all 99k reviews** to keep the latest review per
     order (`distinct on`), then compute the late flag from two text dates.
     That's why it's the slowest query (540 ms). `fct_orders` already has
     `review_score` (latest review) and `is_late` as columns, so the query is
     one scan and a 2-group aggregate (41 ms, 13x faster).
   - (b) on `fct_revenue_monthly` reads ~1.3k pre-summed month x category rows
     instead of ~47k items: 17 pages, 0.3 ms. The catch: it only works for
     whole-month date ranges. That's why the dashboard uses `fct_order_items`,
     which accepts any date range.

**Why staging is not faster than raw:** staging models are **views**. A view is
a saved query, not stored data, so Postgres expands it into the raw query and
runs the same plan (same joins, same casts, same 6,443 pages). Staging comes out
slightly slower because each view adds a few cheap "Subquery Scan" steps, plus
noise. Staging is there to clean names and types *once*, in one place. It isn't
meant to make queries faster: only materialized tables (marts) do that.

## Indexes: what was tried, what was kept

Rule: keep an index only if the plan really uses it **and** the time goes down
by more than the noise.

| candidate index | used by the plan? | result | decision |
|---|---|---|---|
| `fct_order_items (customer_state, purchased_at)` | yes, bitmap scan | still read 3,014 of 3,072 pages: RJ rows are spread over almost every page, so no gain | **removed** |
| `fct_order_items (purchased_at)` | no | the 6-month range is ~42% of rows, so Postgres rightly reads the whole table | **removed** |
| `fct_orders (is_late) where review_score is not null` | no | (c) keeps ~96% of rows, so no index can help | **removed** |
| an index on `category` | n/a | none of the 3 queries filters on category ((b) groups by it) | **not added** |
| `fct_order_items (customer_state, purchased_at) include (order_id, revenue) where is_revenue_order` | yes, **index-only scan** | (a): 3,051 → 139 pages; 1.5x to 1.9x faster in every run | **kept** |
| `fct_order_items (purchased_at) include (category, revenue) where is_revenue_order` | yes, **index-only scan** | (b): 3,051 → 289 pages; faster in 4 of 5 runs (see below) | **kept** |

**Why only covering indexes help here.** A normal index tells Postgres *where*
the matching rows are, but Postgres still has to visit the table to read the
other columns. Here the matching rows are spread over almost every page, so
that saves nothing. A **covering** index (`INCLUDE ...`) stores the extra
columns the query needs inside the index itself, so Postgres answers from the
much smaller index alone ("Index Only Scan", 0 heap fetches). The
`where is_revenue_order` part makes the index **partial**: it skips rows the
dashboard never asks for, which keeps it smaller.

**Median ms, marts without → with index, across all runs I did:**

| query | run 1 | run 2 | run 3 (final) | extra runs (15 each) |
|---|---|---|---|---|
| (a) | 35.8 → 21.0 | 46.5 → 30.3 | 58.8 → 31.7 | |
| (b) | 26.8 → 17.4 | 16.4 → 15.6 | 28.9 → 14.9 | 28.2 → 16.4, 25.9 → 17.6 |

(a) is a clear win: in every run, the slowest index run beat the fastest
no-index run. (b) is a smaller, less steady win. The index plan is very steady
(~15 ms), while the no-index plan (a parallel full-table read) jumps between
~14 and ~30 ms depending on how quickly its parallel workers start. Once
(run 2) it tied. I kept it because it was faster in 4 of 5 measurements and
reads 10x fewer pages, a saving that grows with the data.

**Spot check outside the benchmark:** with State = `SP` (42% of rows) the
index-only scan is still used and reading the rows takes about 20 ms instead of
35 ms. But most of the ~100+ ms goes into `count(distinct order_id)`, which no
index speeds up, so the overall gain is small. With a small state such as `AC`,
the query takes under 1 ms.

**Cost:** 8.4 MB + 5.5 MB of index (the table is 24 MB), and a little more
time for each `dbt build` (creating 2 indexes + a `VACUUM` on a 112k-row table).

### How the indexes are defined (reproducible)

They live in [`fct_order_items.sql`](../olist_analytics/models/marts/fct_order_items.sql)
as dbt `post_hook`s, so every `dbt build` recreates them:

```sql
{{ config(
    post_hook=[
        "create index on {{ this }} (customer_state, purchased_at) include (order_id, revenue) where is_revenue_order",
        "create index on {{ this }} (purchased_at) include (category, revenue) where is_revenue_order",
        {"sql": "vacuum analyze {{ this }}", "transaction": false},
    ]
) }}
```

- **Why post-hooks and not dbt's `indexes` config:** dbt-postgres' `indexes`
  config only supports columns / unique / type. It has no `INCLUDE` or `WHERE`.
- **Why the indexes have no name:** while dbt rebuilds a table, the old copy
  still exists (renamed as a backup), together with its indexes. A fixed index
  name would clash with the backup's index. Without a name, Postgres picks a
  free one (`..._idx` / `..._idx1`, alternating between builds).
- **Why `VACUUM ANALYZE`:** an index-only scan can skip the table only for
  pages Postgres knows are "all-visible". A freshly built table has none of
  those until it's vacuumed, so the query would still visit the table and be
  slow. `VACUUM` can't run inside a transaction, so this hook uses
  `"transaction": false`.

## Honest notes (read before quoting numbers)

- **Absolute times are small.** At ~100k orders, even the slowest raw query
  takes about half a second, and every marts query is under 60 ms. A dashboard
  user will not feel the difference between 15 ms and 30 ms: Metabase's own
  work and the browser take longer than that. The point of this write-up is
  the **ratios and the pages read**, which show how each approach will grow as
  the data grows. It isn't the milliseconds.
- **Noise is large on this machine.** Query (c) runs the identical plan in both
  marts columns, yet its medians differed by up to 37% between runs. Treat any
  difference under ~30% in a single run as noise. Pages read don't vary, so
  they are the more reliable comparison.
- **Warm cache only.** Every number is with the data already in memory (after
  a warm-up). Cold-cache runs (first query after a restart) weren't measured.
  They would favor marts and the indexes even more, because those read fewer pages.
- **One filter value each.** The results depend on the filter (see the SP vs
  AC spot check). Different states or date ranges will give different ratios.

## Reproduce

```bash
docker compose stop metabase            # "nothing else running"
source .venv/bin/activate
(cd olist_analytics && dbt build)       # builds marts + indexes, runs tests
python benchmarks/run_benchmarks.py     # diff check + timing + results table
python benchmarks/run_benchmarks.py --only b_ --runs 15   # one query, more runs
docker compose start metabase
```
