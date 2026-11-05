#!/usr/bin/env python3
"""Build (or update) the "Sales Overview" Metabase dashboard via the API.

Idempotent: cards and the dashboard are looked up by name inside the
"Olist Analytics" collection and updated in place, so running it again
never creates duplicates.

Reads from .env (never committed):
    MB_API_KEY   Metabase API key (admin)
    MB_URL       optional, default http://localhost:3000

Uses only tables in the `marts` schema.

Usage:
    source .venv/bin/activate
    python scripts/metabase/build_sales_dashboard.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTION_NAME = "Olist Analytics"
DASHBOARD_NAME = "Sales Overview"
DB_NAME = "olist"  # Postgres database name configured in Metabase

# Olist data is sparse before 2017-01 and after 2018-08 (<1% of orders),
# so trend charts only show this window.
TREND_START = "2017-01-01"
TREND_END_EXCL = "2018-09-01"
SPARSE_NOTE = (
    "Months before 2017-01 and after 2018-08 are excluded: Olist data is "
    "very sparse there (<1% of orders) and would distort the trend."
)
REVENUE_NOTE = (
    "Revenue = item price + freight, excluding canceled/unavailable orders."
)

# Stable namespace so template-tag ids stay the same on every run.
TAG_NS = uuid.UUID("6f1d2c3a-9b8e-4f6a-8c1d-0e5b7a4c2d10")


# --------------------------------------------------------------------------
# Config + HTTP helpers
# --------------------------------------------------------------------------
def load_env() -> None:
    """Load KEY=VALUE pairs from .env into os.environ (env vars win)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class Metabase:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key})

    def call(self, method: str, path: str, **kwargs):
        resp = self.session.request(method, f"{self.url}/api{path}", timeout=120, **kwargs)
        if resp.status_code >= 400:
            sys.exit(f"ERROR {method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json() if resp.content else None

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, **kw):
        return self.call("POST", path, **kw)

    def put(self, path, **kw):
        return self.call("PUT", path, **kw)


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------
def find_database(mb: Metabase) -> int:
    dbs = mb.get("/database")
    dbs = dbs.get("data", dbs)
    for db in dbs:
        if db["engine"] == "postgres" and db["details"].get("dbname") == DB_NAME:
            return db["id"]
    sys.exit(f"ERROR: no Postgres database '{DB_NAME}' connected in Metabase.")


def field_ids(mb: Metabase, db_id: int) -> dict[tuple[str, str], int]:
    """Map (table, column) -> Metabase field id, for the marts schema only."""
    meta = mb.get(f"/database/{db_id}/metadata")
    return {
        (t["name"], f["name"]): f["id"]
        for t in meta["tables"]
        if t["schema"] == "marts"
        for f in t["fields"]
    }


def get_or_create_collection(mb: Metabase) -> int:
    for c in mb.get("/collection"):
        if c.get("name") == COLLECTION_NAME and not c.get("archived") and not c.get("personal_owner_id"):
            return c["id"]
    created = mb.post("/collection", json={
        "name": COLLECTION_NAME,
        "description": "Dashboards and questions built on the dbt marts schema.",
    })
    print(f"  created collection '{COLLECTION_NAME}' (id {created['id']})")
    return created["id"]


def collection_items(mb: Metabase, coll_id: int, model: str) -> dict[str, int]:
    items = mb.get(f"/collection/{coll_id}/items", params={"models": model})
    items = items.get("data", items)
    return {i["name"]: i["id"] for i in items}


# --------------------------------------------------------------------------
# Card definitions
# --------------------------------------------------------------------------
# Each card's SQL uses up to three field-filter variables. A field filter
# that is left empty becomes "1 = 1" (no filtering).
#   {{date}}     -> purchased_at   (dashboard "Date range")
#   {{category}} -> category       (dashboard "Category")
#   {{state}}    -> customer_state (dashboard "State")
# Tables are referenced WITHOUT aliases because Metabase writes field filters
# as fully qualified "marts"."table"."column".

ITEMS_FILTERED = """
    select *
    from marts.fct_order_items
    where is_revenue_order
      and {{date}} and {{category}} and {{state}}
"""

# Delivered orders (is_late is known); category matches if ANY item of the
# order is in the chosen category.
DELIVERED_ORDERS_WHERE = """
    where fct_orders.is_late is not null
      and {{date}} and {{state}}
      and exists (
          select 1 from marts.fct_order_items
          where fct_order_items.order_id = fct_orders.order_id
            and {{category}}
      )
"""

BRL = {"number_style": "currency", "currency": "BRL", "currency_style": "symbol"}
PCT = {"number_style": "percent", "decimals": 1}


def col(name: str) -> str:
    return f'["name","{name}"]'


CARDS = [
    # ---- 1) KPIs -------------------------------------------------------
    dict(
        key="kpi_revenue", name="Revenue", aliases=["KPI - Revenue"], display="scalar",
        table="fct_order_items",
        description=f"Total revenue for the selected filters. {REVENUE_NOTE}",
        sql=f"with items as ({ITEMS_FILTERED})\nselect sum(revenue) as revenue from items",
        # Shown in millions with 2 decimals (e.g. R$15.74M), not compact "R$16M".
        viz={
            "scalar.compact_primary_number": False,
            "column_settings": {col("revenue"): {
                "number_style": "decimal", "scale": 0.000001, "decimals": 2,
                "prefix": "R$", "suffix": "M",
            }},
        },
    ),
    dict(
        key="kpi_orders", name="Orders", aliases=["KPI - Orders"], display="scalar",
        table="fct_order_items",
        description="Number of distinct orders that count toward revenue "
                    "(canceled/unavailable excluded).",
        sql=f"with items as ({ITEMS_FILTERED})\nselect count(distinct order_id) as orders from items",
        viz={},
    ),
    dict(
        key="kpi_aov", name="Avg order value", aliases=["KPI - Average order value"],
        display="scalar",
        table="fct_order_items",
        description="Revenue / orders. With a category filter, only that "
                    f"category's items count. {REVENUE_NOTE}",
        sql=f"with items as ({ITEMS_FILTERED})\n"
            "select sum(revenue) / nullif(count(distinct order_id), 0) as avg_order_value from items",
        viz={"column_settings": {col("avg_order_value"): {**BRL, "decimals": 2}}},
    ),
    dict(
        key="kpi_customers", name="Customers", aliases=["KPI - Customers"], display="scalar",
        table="fct_order_items",
        description="Distinct real customers (customer_unique_id) with at least "
                    "one revenue order in the selected filters.",
        sql=f"with items as ({ITEMS_FILTERED})\n"
            "select count(distinct customer_unique_id) as customers from items",
        viz={},
    ),
    dict(
        key="kpi_repeat", name="Repeat rate", aliases=["KPI - Repeat customer rate"],
        display="scalar",
        table="fct_order_items",
        description="Share of customers who placed 2 or more revenue orders "
                    "within the selected filters.",
        sql=f"with items as ({ITEMS_FILTERED}),\n"
            "per_customer as (\n"
            "    select customer_unique_id, count(distinct order_id) as orders\n"
            "    from items group by customer_unique_id\n"
            ")\n"
            "select avg(case when orders > 1 then 1.0 else 0 end) as repeat_customer_rate\n"
            "from per_customer",
        viz={"column_settings": {col("repeat_customer_rate"): {**PCT, "decimals": 2}}},
    ),
    # ---- 2) Revenue + orders by month ----------------------------------
    dict(
        key="trend_revenue", name="Revenue and orders by month", display="line",
        table="fct_order_items",
        description=f"Monthly revenue (left axis) and orders (right axis) by "
                    f"purchase month. {SPARSE_NOTE} {REVENUE_NOTE}",
        sql=f"""select
    date_trunc('month', purchased_at)::date as month,
    sum(revenue)                            as revenue,
    count(distinct order_id)                as orders
from marts.fct_order_items
where is_revenue_order
  and purchased_at >= date '{TREND_START}'
  and purchased_at <  date '{TREND_END_EXCL}'
  and {{{{date}}}} and {{{{category}}}} and {{{{state}}}}
group by 1
order by 1""",
        viz={
            "graph.dimensions": ["month"],
            "graph.metrics": ["revenue", "orders"],
            "graph.x_axis.title_text": "Purchase month",
            "graph.y_axis.title_text": "Revenue",
            # Without this, Metabase reuses the left title on the right axis.
            "graph.y_axis.right.title_text": "Orders",
            "series_settings": {
                "revenue": {"axis": "left", "title": "Revenue"},
                "orders": {"axis": "right", "title": "Orders"},
            },
            "column_settings": {
                col("revenue"): {**BRL, "decimals": 0, "column_title": "Revenue"},
                col("orders"): {"column_title": "Orders"},
            },
        },
    ),
    # ---- 3) Top 10 categories ------------------------------------------
    dict(
        key="top_categories", name="Top 10 categories by revenue", display="row",
        table="fct_order_items",
        description=f"The 10 product categories with the highest revenue. {REVENUE_NOTE}",
        sql=f"""with items as ({ITEMS_FILTERED})
select category, sum(revenue) as revenue
from items
group by category
order by revenue desc
limit 10""",
        viz={
            "graph.dimensions": ["category"],
            "graph.metrics": ["revenue"],
            "graph.show_values": True,
            "column_settings": {col("revenue"): {**BRL, "decimals": 0, "column_title": "Revenue"}},
        },
    ),
    # ---- 4) Revenue by state -------------------------------------------
    dict(
        key="state_revenue", name="Revenue by customer state", display="row",
        table="fct_order_items",
        description="The 10 customer states (state at the time of the order) "
                    f"with the highest revenue. {REVENUE_NOTE}",
        sql=f"""with items as ({ITEMS_FILTERED})
select customer_state as state, sum(revenue) as revenue
from items
group by customer_state
order by revenue desc
limit 10""",
        viz={
            "graph.dimensions": ["state"],
            "graph.metrics": ["revenue"],
            "graph.show_values": True,
            "column_settings": {col("revenue"): {**BRL, "decimals": 0, "column_title": "Revenue"}},
        },
    ),
    # ---- 5) Delivery performance by month ------------------------------
    dict(
        key="trend_delivery", name="Late delivery rate and average delivery days by month",
        display="line", table="fct_orders",
        description="Delivered orders only, by purchase month. Late = delivered "
                    "on a later day than the estimated date. Delivery days = "
                    f"calendar days from purchase to delivery. {SPARSE_NOTE}",
        sql=f"""select
    date_trunc('month', fct_orders.purchased_at)::date as month,
    avg(case when fct_orders.is_late then 1.0 else 0 end) as late_delivery_rate,
    avg(fct_orders.delivery_days)                         as avg_delivery_days
from marts.fct_orders
{DELIVERED_ORDERS_WHERE}
  and fct_orders.purchased_at >= date '{TREND_START}'
  and fct_orders.purchased_at <  date '{TREND_END_EXCL}'
group by 1
order by 1""",
        viz={
            "graph.dimensions": ["month"],
            "graph.metrics": ["late_delivery_rate", "avg_delivery_days"],
            "graph.x_axis.title_text": "Purchase month",
            "graph.y_axis.title_text": "Late delivery rate",
            # Without this, Metabase reuses the left title on the right axis.
            "graph.y_axis.right.title_text": "Avg delivery days",
            "series_settings": {
                "late_delivery_rate": {"axis": "left", "title": "Late delivery rate"},
                "avg_delivery_days": {"axis": "right", "title": "Avg delivery days"},
            },
            "column_settings": {
                col("late_delivery_rate"): {**PCT, "column_title": "Late delivery rate"},
                col("avg_delivery_days"): {"decimals": 1, "column_title": "Avg delivery days"},
            },
        },
    ),
    # ---- 6) Key insight: reviews vs lateness ---------------------------
    dict(
        key="review_late", name="Average review score: late vs on-time orders",
        display="bar", table="fct_orders",
        description=None,  # filled in from live data, see insight_description()
        # "status" is a series breakdown so each bar gets its own color;
        # "delivery" is the x-axis label and carries the order count (n).
        sql=f"""with per_group as (
    select
        case when fct_orders.is_late then 'Late' else 'On time' end as status,
        avg(fct_orders.review_score) as avg_review_score,
        count(*)                     as orders
    from marts.fct_orders
    {DELIVERED_ORDERS_WHERE}
      and fct_orders.review_score is not null
    group by 1
)
select
    status || ' (n=' || to_char(orders, 'FM999,999,999') || ')' as delivery,
    status,
    avg_review_score,
    orders
from per_group
order by status desc""",
        viz={
            "graph.dimensions": ["delivery", "status"],
            "graph.metrics": ["avg_review_score"],
            "stackable.stack_type": "stacked",  # one bar per x value, not side by side
            "graph.tooltip_columns": [col("orders")],
            "series_settings": {
                "Late": {"color": "#E8590C", "title": "Late"},
                "On time": {"color": "#98A2B3", "title": "On time"},
            },
            "graph.show_values": True,
            "graph.y_axis.min": 0,
            "graph.y_axis.max": 5,
            "graph.y_axis.auto_range": False,
            "graph.y_axis.title_text": "Average review score (1-5)",
            "column_settings": {col("avg_review_score"): {"decimals": 2}},
        },
    ),
]

# Dashboard filters. Category/state values come from fct_order_items.
PARAMETERS = [
    {"id": "date_range", "name": "Date range", "slug": "date_range",
     "type": "date/range", "sectionId": "date"},
    {"id": "category", "name": "Category", "slug": "category",
     "type": "string/=", "sectionId": "string"},
    {"id": "state", "name": "State", "slug": "state",
     "type": "string/=", "sectionId": "location"},
]
# template tag -> (dashboard parameter id, column name, widget type)
TAGS = {
    "date": ("date_range", "purchased_at", "date/all-options"),
    "category": ("category", "category", "string/="),
    "state": ("state", "customer_state", "string/="),
}

# Markdown text card shown at the top of the dashboard.
INTRO_TEXT = f"""**About this dashboard**
- **Data source:** Olist public Brazilian e-commerce dataset (Kaggle), modeled with dbt (`marts` schema).
- **Revenue** = item price + freight, excluding canceled/unavailable orders.
- **KPI cards** cover all data (unless you set the Date range filter). \
  **Trend charts** show {TREND_START[:7]} to 2018-08 only (data outside this window is very sparse)."""
TEXT_KEY = "intro_text"

# Grid is 24 columns wide. (card key, row, col, width, height)
LAYOUT = [
    (TEXT_KEY, 0, 0, 24, 4),
    # 24 cols / 5 cards: "Orders" has the shortest title, so it is the narrow one.
    ("kpi_revenue", 4, 0, 5, 3),
    ("kpi_orders", 4, 5, 4, 3),
    ("kpi_aov", 4, 9, 5, 3),
    ("kpi_customers", 4, 14, 5, 3),
    ("kpi_repeat", 4, 19, 5, 3),
    ("trend_revenue", 7, 0, 24, 7),
    ("top_categories", 14, 0, 12, 8),
    ("state_revenue", 14, 12, 12, 8),
    ("trend_delivery", 22, 0, 14, 7),
    ("review_late", 22, 14, 10, 7),
]


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def template_tags(card: dict, fields: dict) -> dict:
    tags = {}
    for tag, (_param, column, widget) in TAGS.items():
        if "{{" + tag + "}}" not in card["sql"]:
            continue
        # category lives in fct_order_items even for fct_orders-based cards
        table = "fct_order_items" if tag == "category" else card["table"]
        tags[tag] = {
            "id": str(uuid.uuid5(TAG_NS, f"{card['key']}:{tag}")),
            "name": tag,
            "display-name": tag.capitalize(),
            "type": "dimension",
            "dimension": ["field", fields[(table, column)], None],
            "widget-type": widget,
        }
    return tags


def upsert_cards(mb: Metabase, db_id: int, coll_id: int, fields: dict) -> dict[str, int]:
    existing = collection_items(mb, coll_id, "card")
    ids = {}
    for card in CARDS:
        body = {
            "name": card["name"],
            "description": card["description"],
            "display": card["display"],
            "collection_id": coll_id,
            "visualization_settings": card["viz"],
            "dataset_query": {
                "type": "native",
                "database": db_id,
                "native": {"query": card["sql"].strip(), "template-tags": template_tags(card, fields)},
            },
        }
        # Match by current name first, then by old names (renamed cards).
        match = next((n for n in [card["name"], *card.get("aliases", [])] if n in existing), None)
        if match:
            cid = existing[match]
            if card["description"] is None:
                body.pop("description")  # keep the live-data description
            mb.put(f"/card/{cid}", json=body)
            renamed = f"  (was '{match}')" if match != card["name"] else ""
            print(f"  updated card {cid:>4}  {card['name']}{renamed}")
        else:
            cid = mb.post("/card", json=body)["id"]
            print(f"  created card {cid:>4}  {card['name']}")
        ids[card["key"]] = cid
    return ids


def run_card(mb: Metabase, card_id: int) -> dict:
    return mb.post(f"/card/{card_id}/query", json={})


def insight_description(mb: Metabase, card_id: int) -> str:
    """Describe the review-vs-lateness insight with numbers from the data."""
    rows = {r[0]: r for r in run_card(mb, card_id)["data"]["rows"]}
    late, ontime = rows.get("Late"), rows.get("On time")
    base = ("KEY INSIGHT. Delivered orders with a review. Late = delivered on a "
            "later day than the estimated date.")
    if not late or not ontime:
        return base
    return (f"{base} Late orders average {float(late[1]):.2f} stars "
            f"({late[2]:,} orders) vs {float(ontime[1]):.2f} for on-time orders "
            f"({ontime[2]:,} orders), a drop of {float(ontime[1]) - float(late[1]):.2f} "
            "stars: delivery speed is a major driver of customer satisfaction.")


def upsert_dashboard(mb: Metabase, coll_id: int, card_ids: dict[str, int]) -> int:
    existing = collection_items(mb, coll_id, "dashboard")
    desc = ("Revenue, orders, customers, delivery performance and reviews for "
            "the Olist marketplace. Built by scripts/metabase/build_sales_dashboard.py "
            "from the dbt marts schema - edit the script, not the UI.")
    if DASHBOARD_NAME in existing:
        dash_id = existing[DASHBOARD_NAME]
        print(f"  found dashboard {dash_id}  {DASHBOARD_NAME}")
    else:
        dash_id = mb.post("/dashboard", json={
            "name": DASHBOARD_NAME, "collection_id": coll_id, "description": desc,
        })["id"]
        print(f"  created dashboard {dash_id}  {DASHBOARD_NAME}")

    # Reuse existing dashcard ids (per card) so the update is in place.
    current = mb.get(f"/dashboard/{dash_id}").get("dashcards", [])
    dashcard_id_by_card = {dc["card_id"]: dc["id"] for dc in current if dc.get("card_id")}
    text_dashcard_ids = [
        dc["id"] for dc in current
        if not dc.get("card_id")
        and dc.get("visualization_settings", {}).get("virtual_card", {}).get("display") == "text"
    ]

    cards_by_key = {c["key"]: c for c in CARDS}
    dashcards = []
    for i, (key, row, column, width, height) in enumerate(LAYOUT):
        if key == TEXT_KEY:
            # Text card: no saved question behind it. Reuse the existing one.
            dashcards.append({
                "id": text_dashcard_ids[0] if text_dashcard_ids else -(i + 1),
                "card_id": None,
                "row": row, "col": column, "size_x": width, "size_y": height,
                "parameter_mappings": [],
                "visualization_settings": {
                    "virtual_card": {"name": None, "display": "text", "archived": False,
                                     "dataset_query": {}, "visualization_settings": {}},
                    "text": INTRO_TEXT,
                },
            })
            continue
        cid = card_ids[key]
        sql = cards_by_key[key]["sql"]
        mappings = [
            {
                "parameter_id": param_id,
                "card_id": cid,
                "target": ["dimension", ["template-tag", tag], {"stage-number": 0}],
            }
            for tag, (param_id, _c, _w) in TAGS.items()
            if "{{" + tag + "}}" in sql
        ]
        dashcards.append({
            "id": dashcard_id_by_card.get(cid, -(i + 1)),  # negative id = new
            "card_id": cid,
            "row": row, "col": column, "size_x": width, "size_y": height,
            "parameter_mappings": mappings,
            "visualization_settings": {},
        })

    mb.put(f"/dashboard/{dash_id}", json={
        "name": DASHBOARD_NAME,
        "description": desc,
        "collection_id": coll_id,
        "parameters": PARAMETERS,
        "dashcards": dashcards,
    })
    print(f"  saved dashboard layout: {len(dashcards)} cards, {len(PARAMETERS)} filters")
    return dash_id


# --------------------------------------------------------------------------
# Check: every card must run, with no filters and with all filters set
# --------------------------------------------------------------------------
TEST_FILTERS = [
    {"id": "date_range", "type": "date/range", "value": "2017-06-01~2018-03-31"},
    {"id": "category", "type": "string/=", "value": ["health_beauty"]},
    {"id": "state", "type": "string/=", "value": ["SP"]},
]


def check_dashboard(mb: Metabase, dash_id: int) -> bool:
    dash = mb.get(f"/dashboard/{dash_id}")
    ok = True
    print(f"\n  {'card':<56} {'no filter':>10} {'filtered':>10}")
    for dc in sorted(dash["dashcards"], key=lambda d: (d["row"], d["col"])):
        if not dc.get("card_id"):
            print(f"  {'(text card)':<56} {'ok':>10}")
            continue
        cid, name = dc["card_id"], dc["card"]["name"]
        mapped = {m["parameter_id"] for m in dc["parameter_mappings"]}
        results, first_row = [], None
        for params in ([], [p for p in TEST_FILTERS if p["id"] in mapped]):
            res = mb.post(
                f"/dashboard/{dash_id}/dashcard/{dc['id']}/card/{cid}/query",
                json={"parameters": params},
            )
            if res.get("status") != "completed" or res.get("error"):
                ok = False
                results.append("ERROR")
                print(f"    ! {name}: {res.get('error')}")
            else:
                results.append(f"{res['row_count']} rows")
                if not params:
                    first_row = res["data"]["rows"][0] if res["data"]["rows"] else None
        print(f"  {name:<56} {results[0]:>10} {results[1]:>10}  filters={sorted(mapped)}")
        print(f"    first row (no filter): {first_row}")
    return ok


def main() -> None:
    load_env()
    api_key = os.environ.get("MB_API_KEY")
    if not api_key:
        sys.exit("ERROR: MB_API_KEY is not set (add it to .env).")
    mb = Metabase(os.environ.get("MB_URL", "http://localhost:3000"), api_key)

    print("1) Looking up database and fields")
    db_id = find_database(mb)
    fields = field_ids(mb, db_id)
    needed = {("fct_order_items", c) for c in ("purchased_at", "category", "customer_state")} | {
        ("fct_orders", c) for c in ("purchased_at", "customer_state")
    }
    missing = needed - fields.keys()
    if missing:
        sys.exit(f"ERROR: Metabase has not synced these marts fields yet: {sorted(missing)}")
    print(f"  database id {db_id}, {len(fields)} marts fields")

    print("2) Collection")
    coll_id = get_or_create_collection(mb)

    print("3) Cards")
    card_ids = upsert_cards(mb, db_id, coll_id, fields)
    mb.put(f"/card/{card_ids['review_late']}",
           json={"description": insight_description(mb, card_ids["review_late"])})

    print("4) Dashboard")
    dash_id = upsert_dashboard(mb, coll_id, card_ids)

    print("5) Checking every card")
    ok = check_dashboard(mb, dash_id)
    print(f"\nDashboard: {mb.url}/dashboard/{dash_id}")
    if not ok:
        sys.exit("Some cards failed - see errors above.")
    print("All cards ran without errors.")


if __name__ == "__main__":
    main()
