"""Benchmark the dashboard queries on raw vs staging vs marts (vs marts + indexes).

Usage (from the repo root, with Postgres running):
    source .venv/bin/activate
    python benchmarks/run_benchmarks.py            # 1 warm-up + 5 measured runs
    python benchmarks/run_benchmarks.py --runs 9   # more runs
    python benchmarks/run_benchmarks.py --only b_  # one query only

What it does:
1. ANALYZE the raw and marts tables, so the planner has fresh statistics.
2. Correctness: runs every query file in benchmarks/sql/, saves the result to
   benchmarks/results/<file>.csv and checks it is byte-identical to the raw
   version of the same query. Stops if any version differs.
3. Timing: for each file, runs EXPLAIN (ANALYZE, BUFFERS) once as a warm-up,
   then N times, and keeps the median "Execution Time". Runs are interleaved
   (run 1 of every case, then run 2, ...) so background noise is spread evenly.
   Marts files are measured twice:
     - "marts":        index scans disabled for the session = same plan as
                       if the indexes did not exist;
     - "marts + idx":  normal settings, so the planner may use the indexes
                       that dbt created (see models/marts/_marts.yml / configs).
4. Prints a results table and writes it to benchmarks/results/results.md
   (plus raw numbers in results.json).

File naming: <query>__<layer>.sql, layer in {raw, staging, marts, marts_*}.
Credentials come from .env (PG_USER, PG_PASSWORD); nothing is hardcoded.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import statistics
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "benchmarks" / "sql"
RESULTS_DIR = ROOT / "benchmarks" / "results"

TABLES_TO_ANALYZE = [
    "raw.orders", "raw.customers", "raw.order_items", "raw.products",
    "raw.product_category_name_translation", "raw.order_reviews",
    "marts.fct_orders", "marts.fct_order_items", "marts.fct_revenue_monthly",
]
ROW_COUNT_TABLES = TABLES_TO_ANALYZE

# Session settings that make the planner ignore indexes (= "no indexes" plan).
NO_INDEX_SETTINGS = (
    "set enable_indexscan = off; set enable_bitmapscan = off; "
    "set enable_indexonlyscan = off;"
)
DEFAULT_SETTINGS = "reset enable_indexscan; reset enable_bitmapscan; reset enable_indexonlyscan;"


def load_env() -> None:
    """Load KEY=VALUE pairs from .env into os.environ (real env vars win)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect():
    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5433")),
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        dbname="olist",
    )
    conn.autocommit = True
    return conn


def discover() -> dict[str, dict[str, Path]]:
    """{query_name: {layer: path}} from files named <query>__<layer>.sql."""
    queries: dict[str, dict[str, Path]] = {}
    for path in sorted(SQL_DIR.glob("*__*.sql")):
        query, layer = path.stem.split("__", 1)
        queries.setdefault(query, {})[layer] = path
    return queries


def read_sql(path: Path) -> str:
    return path.read_text().strip().rstrip(";")


def result_csv(cur, sql: str) -> str:
    cur.execute(sql)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([d.name for d in cur.description])
    writer.writerows(cur.fetchall())
    return buf.getvalue()


def check_results(cur, queries) -> bool:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    print("\n== Correctness: every layer must return exactly the raw result ==")
    for query, layers in queries.items():
        outputs = {layer: result_csv(cur, read_sql(p)) for layer, p in layers.items()}
        for layer, text in outputs.items():
            (RESULTS_DIR / f"{query}__{layer}.csv").write_text(text)
        reference = outputs["raw"]
        for layer, text in outputs.items():
            if layer == "raw":
                continue
            same = text == reference
            ok &= same
            rows = text.count("\n") - 1
            print(f"  {query:<18} raw vs {layer:<14} {rows:>3} rows  "
                  f"{'IDENTICAL' if same else 'DIFFERENT'}")
    return ok


def explain_once(cur, sql: str) -> dict:
    cur.execute(f"explain (analyze, buffers, format json) {sql}")
    plan = cur.fetchone()[0][0]
    top = plan["Plan"]
    jit = plan.get("JIT", {}).get("Timing", {}).get("Total", 0.0)
    return {
        "execution_ms": plan["Execution Time"],
        "planning_ms": plan["Planning Time"],
        "shared_hit": top.get("Shared Hit Blocks", 0),
        "shared_read": top.get("Shared Read Blocks", 0),
        "jit_ms": jit,
    }


def run_with(cur, sql: str, settings: str) -> dict:
    cur.execute(settings)
    try:
        return explain_once(cur, sql)
    finally:
        cur.execute(DEFAULT_SETTINGS)


def summarize(samples: list[dict]) -> dict:
    times = [s["execution_ms"] for s in samples]
    return {
        "median_ms": statistics.median(times),
        "min_ms": min(times),
        "max_ms": max(times),
        "planning_ms": statistics.median(s["planning_ms"] for s in samples),
        "buffers": samples[-1]["shared_hit"] + samples[-1]["shared_read"],
        "jit_ms": statistics.median(s["jit_ms"] for s in samples),
        "samples_ms": times,
    }


def ratio(base: float | None, other: float | None) -> str:
    if base is None or other is None or other == 0:
        return "-"
    return f"{base / other:.1f}x"


def fmt(ms: float | None) -> str:
    return "-" if ms is None else f"{ms:.2f}"


def build_table(results: dict) -> str:
    header = ("| query | raw ms | staging ms | marts ms | marts+idx ms | "
              "raw / marts | raw / marts+idx |")
    lines = [header, "|---|---:|---:|---:|---:|---:|---:|"]
    for query, layers in results.items():
        raw = layers.get("raw", {}).get("default", {}).get("median_ms")
        stg = layers.get("staging", {}).get("default", {}).get("median_ms")
        for layer in sorted(k for k in layers if k.startswith("marts")):
            m = layers[layer]["no_index"]["median_ms"]
            mi = layers[layer]["default"]["median_ms"]
            name = query if layer == "marts" else f"{query} ({layer})"
            show_base = layer == "marts"
            lines.append(
                f"| {name} | {fmt(raw) if show_base else '-'} | "
                f"{fmt(stg) if show_base else '-'} | {fmt(m)} | {fmt(mi)} | "
                f"{ratio(raw, m)} | {ratio(raw, mi)} |"
            )
    return "\n".join(lines)


def build_detail_table(results: dict) -> str:
    lines = ["| file | mode | median ms | min ms | max ms | planning ms | buffers | JIT ms |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for query, layers in results.items():
        for layer, modes in layers.items():
            for mode, r in modes.items():
                lines.append(
                    f"| {query}__{layer} | {mode} | {r['median_ms']:.2f} | {r['min_ms']:.2f} | "
                    f"{r['max_ms']:.2f} | {r['planning_ms']:.2f} | {r['buffers']} | {r['jit_ms']:.2f} |"
                )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--only", help="run only queries whose name contains this text")
    args = parser.parse_args()

    load_env()
    conn = connect()
    cur = conn.cursor()

    cur.execute("select version()")
    print(cur.fetchone()[0])
    for table in TABLES_TO_ANALYZE:
        cur.execute(f"analyze {table}")

    print("\n== Dataset size ==")
    for table in ROW_COUNT_TABLES:
        cur.execute(f"select count(*) from {table}")
        print(f"  {table:<42} {cur.fetchone()[0]:>9,}")

    cur.execute("select schemaname || '.' || indexname from pg_indexes "
                "where schemaname = 'marts' order by 1")
    indexes = [r[0] for r in cur.fetchall()]
    print("\n== Indexes on marts ==")
    print("  " + ("\n  ".join(indexes) if indexes else "(none)"))

    queries = discover()
    if args.only:
        queries = {q: l for q, l in queries.items() if args.only in q}
    if not check_results(cur, queries):
        print("\nERROR: some versions return different results. Fix before timing.")
        return 1

    # One "case" = (query, layer, mode). Marts are measured with and without indexes.
    cases = []
    for query, layers in queries.items():
        for layer, path in layers.items():
            modes = {"default": DEFAULT_SETTINGS}
            if layer.startswith("marts"):
                modes = {"no_index": NO_INDEX_SETTINGS, "default": DEFAULT_SETTINGS}
            for mode, settings in modes.items():
                cases.append((query, layer, mode, read_sql(path), settings))

    print(f"\n== Timing: {args.warmup} warm-up + {args.runs} runs, median Execution Time ==")
    print("  (runs are interleaved: run 1 of every case, then run 2, ... so background")
    print("   noise is spread evenly instead of hitting one query)")
    for _ in range(args.warmup):
        for _, _, _, sql, settings in cases:
            run_with(cur, sql, settings)
    samples: dict = {}
    for _ in range(args.runs):
        for query, layer, mode, sql, settings in cases:
            samples.setdefault((query, layer, mode), []).append(run_with(cur, sql, settings))

    results: dict = {}
    for (query, layer, mode), s in samples.items():
        r = summarize(s)
        results.setdefault(query, {}).setdefault(layer, {})[mode] = r
        print(f"  {query:<18} {layer:<14} {mode:<9} median {r['median_ms']:9.2f} ms "
              f"(runs: {', '.join(f'{t:.1f}' for t in r['samples_ms'])})")

    table = build_table(results)
    detail = build_detail_table(results)
    print("\n== Results (median execution time) ==\n")
    print(table)
    print("\n== Details ==\n")
    print(detail)

    (RESULTS_DIR / "results.md").write_text(
        f"Indexes on marts: {', '.join(indexes) if indexes else 'none'}\n\n"
        f"{table}\n\n{detail}\n"
    )
    (RESULTS_DIR / "results.json").write_text(
        json.dumps({"indexes": indexes, "results": results}, indent=2)
    )
    print(f"\nSaved to {RESULTS_DIR.relative_to(ROOT)}/results.md and results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
