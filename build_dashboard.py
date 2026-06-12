#!/usr/bin/env python3
"""
JRBG Universal MTD Dashboard Builder
=====================================
Queries MotherDuck → builds self-contained HTML → deploys via GitHub Pages.

Architecture:
  SAP / Zoho POS  →  MotherDuck (Data Warehouse)  →  This Script (GitHub Actions)
       ↓                      ↓                              ↓
  Daily POS sync       SQL queries run              Dashboard HTML rebuilt
                                                          ↓
                                                   GitHub Pages updated
                                                          ↓
                                                   Same URL, fresh data

Usage:
  python build_dashboard.py --region KL
  python build_dashboard.py --region TN
  python build_dashboard.py --region ALL
"""

import duckdb
import json
import os
import sys
import argparse
import statistics
from datetime import datetime, timedelta
from pathlib import Path

# ===================================================================
# CONFIG
# ===================================================================
MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN")
OUTPUT_DIR = Path("docs")
TEMPLATE_DIR = Path("templates")
LOGO_PATH = Path("assets/logo.jpeg")

# Region → POS system → Database mapping
REGIONS = {
    "KL": {
        "name": "Kerala (KL)",
        "pos": "Zakya",
        "invoice_table": "my_db.zakya.invoices",
        "item_table": "bronze_zakya.landing.export_invoices",
        "item_level": True,
        "date_col": "invoice_date",
        "store_col": "store_name",
        "sales_col": "total",
        "status_filter": "status != 'void'",
        "exclude_stores": ["Karakkamandapam"],
    },
    "TN": {
        "name": "Tamil Nadu (TN)",
        "pos": "Gofrugal",
        "invoice_table": "bronze_gofrugal.landing.sales_item_wise",
        "item_table": "bronze_gofrugal.landing.sales_item_wise",
        "item_level": True,
        "date_col": "bill_date",
        "store_col": "store_name",
        "sales_col": "net_amount",
        "status_filter": "1=1",
        "exclude_stores": [],
    },
}

# HSN → LOB mapping (Zakya only)
HSN_LOB_SQL = """
CASE
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2)
       IN ('52','53','54','55','56','58','61','62','63') THEN 'Fashion'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) = '64' THEN 'Footwear'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2)
       IN ('02','03','04','07','08','09','10','11','12','15','16','17','19','20','21','22') THEN 'Grocery'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) IN ('33','34') THEN 'Health & Beauty'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) = '71' THEN 'Jewelry'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) = '95' THEN 'Toys'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) = '91' THEN 'Watches'
  WHEN LEFT(json_extract_string(_payload, '$."HSN/SAC"'),2) = '90' THEN 'Eyewear'
  ELSE 'Home & Others'
END
"""


# ===================================================================
# DATABASE
# ===================================================================
def connect():
    """Connect to MotherDuck."""
    if not MOTHERDUCK_TOKEN:
        print("❌ MOTHERDUCK_TOKEN not set")
        sys.exit(1)
    conn = duckdb.connect(f"md:my_db?motherduck_token={MOTHERDUCK_TOKEN}")
    print("✅ Connected to MotherDuck")
    return conn


def get_period():
    """Return first-of-month and yesterday."""
    today = datetime.now()
    first = today.replace(day=1).strftime("%Y-%m-%d")
    yest = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    month_name = today.strftime("%B %Y")
    return first, yest, month_name


# ===================================================================
# QUERIES
# ===================================================================
def query_store_mtd(conn, cfg, start, end):
    """Store-wise MTD aggregates."""
    excl = " AND ".join([f"{cfg['store_col']} != '{s}'" for s in cfg["exclude_stores"]])
    if excl:
        excl = f"AND {excl}"
    sql = f"""
    SELECT {cfg['store_col']} as store_name,
           COUNT(*) as bills,
           ROUND(SUM({cfg['sales_col']})) as mtd_sales,
           ROUND(AVG({cfg['sales_col']})) as avg_basket,
           COUNT(DISTINCT {cfg['date_col']}) as days
    FROM {cfg['invoice_table']}
    WHERE {cfg['date_col']} >= '{start}' AND {cfg['date_col']} <= '{end}'
          AND {cfg['status_filter']} {excl}
    GROUP BY 1 ORDER BY mtd_sales DESC
    """
    return conn.execute(sql).fetchall()


def query_daily(conn, cfg, start, end):
    """Daily totals."""
    excl = " AND ".join([f"{cfg['store_col']} != '{s}'" for s in cfg["exclude_stores"]])
    if excl:
        excl = f"AND {excl}"
    sql = f"""
    SELECT {cfg['date_col']} as dt,
           COUNT(*) as bills,
           ROUND(SUM({cfg['sales_col']})) as sales
    FROM {cfg['invoice_table']}
    WHERE {cfg['date_col']} >= '{start}' AND {cfg['date_col']} <= '{end}'
          AND {cfg['status_filter']} {excl}
    GROUP BY 1 ORDER BY 1
    """
    return conn.execute(sql).fetchall()


def query_store_daily(conn, cfg, start, end):
    """Store × day matrix."""
    excl = " AND ".join([f"{cfg['store_col']} != '{s}'" for s in cfg["exclude_stores"]])
    if excl:
        excl = f"AND {excl}"
    sql = f"""
    SELECT {cfg['store_col']} as store_name,
           {cfg['date_col']} as dt,
           COUNT(*) as bills,
           ROUND(SUM({cfg['sales_col']})) as sales
    FROM {cfg['invoice_table']}
    WHERE {cfg['date_col']} >= '{start}' AND {cfg['date_col']} <= '{end}'
          AND {cfg['status_filter']} {excl}
    GROUP BY 1, 2 ORDER BY 1, 2
    """
    return conn.execute(sql).fetchall()


def query_prev_month(conn, cfg, start, end):
    """Previous month equivalent MTD."""
    from dateutil.relativedelta import relativedelta
    d1 = datetime.strptime(start, "%Y-%m-%d")
    d2 = datetime.strptime(end, "%Y-%m-%d")
    ps = (d1 - relativedelta(months=1)).strftime("%Y-%m-%d")
    pe = (d2 - relativedelta(months=1)).strftime("%Y-%m-%d")
    excl = " AND ".join([f"{cfg['store_col']} != '{s}'" for s in cfg["exclude_stores"]])
    if excl:
        excl = f"AND {excl}"
    sql = f"""
    SELECT {cfg['store_col']} as store_name,
           ROUND(SUM({cfg['sales_col']})) as prev_sales
    FROM {cfg['invoice_table']}
    WHERE {cfg['date_col']} >= '{ps}' AND {cfg['date_col']} <= '{pe}'
          AND {cfg['status_filter']} {excl}
    GROUP BY 1
    """
    return conn.execute(sql).fetchall()


def query_lob_daily(conn, cfg, start, end):
    """LOB-wise daily (Zakya only — uses HSN from item payload)."""
    if cfg["pos"] != "Zakya":
        return []
    sql = f"""
    SELECT _business_date as dt,
           {HSN_LOB_SQL} as lob,
           ROUND(SUM(CAST(json_extract_string(_payload, '$."Item Total"') AS DOUBLE))) as revenue,
           COUNT(*) as items
    FROM {cfg['item_table']}
    WHERE _business_date >= '{start}' AND _business_date <= '{end}'
    GROUP BY 1, 2 ORDER BY 1, 3 DESC
    """
    return conn.execute(sql).fetchall()


# ===================================================================
# DATA TRANSFORMATION
# ===================================================================
def build_data_package(conn, region_code):
    """Query everything and build a JSON-ready data package."""
    cfg = REGIONS[region_code]
    start, end, month = get_period()
    
    print(f"📅 Period: {start} → {end} ({month})")
    print(f"📍 Region: {cfg['name']} ({cfg['pos']} POS)")
    
    # Query all data
    print("  📊 Store MTD...")
    store_mtd = query_store_mtd(conn, cfg, start, end)
    print(f"     → {len(store_mtd)} stores")
    
    print("  📊 Daily totals...")
    daily = query_daily(conn, cfg, start, end)
    print(f"     → {len(daily)} days")
    
    print("  📊 Store × day...")
    store_daily = query_store_daily(conn, cfg, start, end)
    print(f"     → {len(store_daily)} rows")
    
    print("  📊 Previous month...")
    try:
        prev = query_prev_month(conn, cfg, start, end)
        prev_map = {r[0]: r[1] for r in prev}
        print(f"     → {len(prev)} stores")
    except:
        prev_map = {}
        print("     ⚠️ No previous month data")
    
    print("  📊 LOB daily...")
    try:
        lob_daily = query_lob_daily(conn, cfg, start, end)
        print(f"     → {len(lob_daily)} LOB-day rows")
    except:
        lob_daily = []
        print("     ⚠️ No LOB data")
    
    # Transform stores
    stores = []
    for r in store_mtd:
        name, bills, sales, basket, days = r
        prev_sales = prev_map.get(name, 0)
        mom = round((sales - prev_sales) / prev_sales * 100, 1) if prev_sales > 0 else None
        stores.append({
            "name": name,
            "bills": int(bills),
            "sales": round(sales),
            "sales_lakhs": round(sales / 100000, 1),
            "avg_basket": int(basket),
            "days": int(days),
            "prev_sales": round(prev_sales),
            "prev_lakhs": round(prev_sales / 100000, 1),
            "mom_pct": mom,
        })
    
    # Transform daily
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily_data = []
    for r in daily:
        dt, bills, sales = r
        daily_data.append({
            "date": str(dt),
            "label": f"{dt.strftime('%b %d')} {day_names[dt.weekday()]}",
            "day": day_names[dt.weekday()],
            "bills": int(bills),
            "sales": round(sales),
            "sales_lakhs": round(sales / 100000, 1),
        })
    
    # Transform store × day
    sd_map = {}
    for r in store_daily:
        store, dt, bills, sales = r
        if store not in sd_map:
            sd_map[store] = []
        sd_map[store].append({
            "date": str(dt),
            "bills": int(bills),
            "sales": round(sales),
            "sales_lakhs": round(sales / 100000, 1),
        })
    
    # Transform LOB daily
    lob_map = {}
    for r in lob_daily:
        dt, lob, rev, items = r
        if lob not in lob_map:
            lob_map[lob] = []
        lob_map[lob].append({
            "date": str(dt),
            "revenue_lakhs": round(rev / 100000, 1),
            "items": int(items),
        })
    
    # Statistics
    daily_sales = [d["sales_lakhs"] for d in daily_data]
    mean_daily = round(statistics.mean(daily_sales), 1) if daily_sales else 0
    sd_daily = round(statistics.stdev(daily_sales), 1) if len(daily_sales) > 1 else 0
    
    total_sales = sum(s["sales"] for s in stores)
    total_bills = sum(s["bills"] for s in stores)
    
    return {
        "meta": {
            "region": region_code,
            "region_name": cfg["name"],
            "pos_system": cfg["pos"],
            "period_start": start,
            "period_end": end,
            "month": month,
            "days": len(daily_data),
            "store_count": len(stores),
            "built_at": datetime.now().strftime("%d %b %Y, %I:%M %p IST"),
        },
        "totals": {
            "mtd_sales": round(total_sales),
            "mtd_sales_cr": round(total_sales / 10000000, 2),
            "bills": total_bills,
            "avg_basket": round(total_sales / total_bills) if total_bills else 0,
        },
        "stats": {
            "mean_daily_lakhs": mean_daily,
            "sd_daily_lakhs": sd_daily,
            "cv_pct": round(sd_daily / mean_daily * 100, 1) if mean_daily else 0,
        },
        "stores": stores,
        "daily": daily_data,
        "store_daily": sd_map,
        "lob_daily": lob_map,
    }


# ===================================================================
# HTML GENERATION
# ===================================================================
def build_html(data):
    """Inject data into HTML template or generate standalone."""
    template_path = TEMPLATE_DIR / "dashboard_template.html"
    
    if template_path.exists():
        print(f"  📄 Using template: {template_path}")
        with open(template_path, "r") as f:
            html = f.read()
        
        # Inject data
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        html = html.replace(
            "/* __LIVE_DATA_INJECTION_POINT__ */",
            f"window.__LIVE__ = {data_json};"
        )
        html = html.replace("__LAST_UPDATED__", data["meta"]["built_at"])
        return html
    else:
        print(f"  ⚠️ No template found at {template_path}")
        print(f"  📄 Generating data JSON for manual template injection")
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ===================================================================
# MAIN
# ===================================================================
def main():
    parser = argparse.ArgumentParser(description="JRBG Dashboard Builder")
    parser.add_argument("--region", default="KL", choices=["KL", "TN", "ALL"])
    args = parser.parse_args()
    
    print("=" * 64)
    print("  JRBG Universal MTD Dashboard Builder")
    print("  SAP/Zoho POS → MotherDuck → GitHub Pages")
    print("=" * 64)
    
    conn = connect()
    
    regions = ["KL", "TN"] if args.region == "ALL" else [args.region]
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    for region in regions:
        if region not in REGIONS:
            print(f"❌ Unknown region: {region}")
            continue
        
        print(f"\n{'─' * 48}")
        print(f"  Building: {REGIONS[region]['name']}")
        print(f"{'─' * 48}")
        
        # Build data
        data = build_data_package(conn, region)
        
        # Generate HTML
        html = build_html(data)
        
        # Write output
        if len(regions) == 1:
            out_file = OUTPUT_DIR / "index.html"
        else:
            out_file = OUTPUT_DIR / f"dashboard_{region.lower()}.html"
        
        with open(out_file, "w") as f:
            f.write(html)
        
        size_kb = len(html) // 1024
        print(f"\n  ✅ Saved: {out_file} ({size_kb} KB)")
        print(f"  📊 MTD Sales: ₹{data['totals']['mtd_sales_cr']} Cr")
        print(f"  🧾 Bills: {data['totals']['bills']:,}")
        print(f"  🏪 Stores: {data['meta']['store_count']}")
        print(f"  📅 Days: {data['meta']['days']}")
    
    # If ALL mode, create index page
    if args.region == "ALL":
        idx = """<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>JRBG Dashboard</title>
        <meta http-equiv="refresh" content="0;url=dashboard_kl.html">
        </head><body>
        <a href="dashboard_kl.html">KL Dashboard</a> | 
        <a href="dashboard_tn.html">TN Dashboard</a>
        </body></html>"""
        with open(OUTPUT_DIR / "index.html", "w") as f:
            f.write(idx)
    
    print(f"\n{'=' * 64}")
    print(f"  ✅ BUILD COMPLETE")
    print(f"  🌐 Deploy via: GitHub Pages → docs/ folder")
    print(f"{'=' * 64}")


if __name__ == "__main__":
    main()
