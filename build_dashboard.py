#!/usr/bin/env python3
"""
JRBG KL MTD Dashboard Builder v2
Queries MotherDuck, replaces sample data directly in template HTML.
"""
import duckdb, json, os, sys, re, argparse, statistics
from datetime import datetime, timedelta
from pathlib import Path

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN")
OUTPUT_DIR = Path("docs")
TEMPLATE_DIR = Path("templates")
EXCLUDE = ["Karakkamandapam"]

STORE_MAP = {
    "Attakulangara":          {"code":"ATK STORE","sm":"Zainulabudeen","cl":"Balan"},
    "Pazhavangadi East Fort": {"code":"PKD STORE","sm":"Symon","cl":"Balan"},
    "Attingal":               {"code":"ATL STORE","sm":"Dhanalakshmi","cl":"Balan"},
    "KUDAPPANAKUNNU":         {"code":"KNP STORE","sm":"Sasikumar","cl":"Balan"},
    "Ulloor":                 {"code":"ULR STORE","sm":"Muniappan","cl":"Balan"},
    "Vellayambalam":          {"code":"KKM STORE","sm":"\u2014","cl":"Balan"},
    "Thirumala":              {"code":"TML STORE","sm":"Arun Yerol","cl":"Thilak"},
    "Neyyantinkara":          {"code":"NTK STORE","sm":"Midhun","cl":"Thilak"},
    "Kaniyapuram":            {"code":"KAT STORE","sm":"Madasami","cl":"Thilak"},
    "Panachamoodu":           {"code":"PMD STORE","sm":"Mariappan","cl":"Thilak"},
    "Mall Of Travancore":     {"code":"MOT STORE","sm":"Srinivasan","cl":"Thilak"},
    "Nedumangadu":            {"code":"NDM STORE","sm":"Anish","cl":"Sherry"},
    "Kattakada":              {"code":"KUD STORE","sm":"Rajesh Unnikrishnan","cl":"Sherry"},
    "Enchakkal":              {"code":"EKL STORE","sm":"Aswathy","cl":"Sherry"},
    "Courtallam":             {"code":"COURTALLAM (VAM)","sm":"Murali Venkatesh","cl":"Sherry"},
}

def connect():
    if not MOTHERDUCK_TOKEN:
        print("ERROR: MOTHERDUCK_TOKEN not set"); sys.exit(1)
    conn = duckdb.connect(f"md:my_db?motherduck_token={MOTHERDUCK_TOKEN}")
    print("Connected to MotherDuck")
    return conn

def get_period():
    today = datetime.now()
    first = today.replace(day=1).strftime("%Y-%m-%d")
    yest = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return first, yest

def q(conn, sql):
    return conn.execute(sql).fetchall()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="KL")
    args = parser.parse_args()

    print("=" * 60)
    print("  JRBG Dashboard Builder v2 — Direct Data Replacement")
    print("=" * 60)

    conn = connect()
    start, end = get_period()
    print(f"Period: {start} to {end}")

    excl_sql = " AND ".join([f"store_name != '{s}'" for s in EXCLUDE])

    # Store MTD
    rows = q(conn, f"""
        SELECT store_name, COUNT(*) as bills, ROUND(SUM(total)) as sales,
               ROUND(AVG(total)) as basket
        FROM zakya.invoices
        WHERE invoice_date >= '{start}' AND invoice_date <= '{end}'
              AND status != 'void' AND {excl_sql}
        GROUP BY store_name ORDER BY sales DESC
    """)
    print(f"  Stores: {len(rows)}")

    # Previous month
    try:
        from dateutil.relativedelta import relativedelta
        d1 = datetime.strptime(start, "%Y-%m-%d")
        d2 = datetime.strptime(end, "%Y-%m-%d")
        ps = (d1 - relativedelta(months=1)).strftime("%Y-%m-%d")
        pe = (d2 - relativedelta(months=1)).strftime("%Y-%m-%d")
        prev = q(conn, f"""
            SELECT store_name, ROUND(SUM(total)) as sales
            FROM zakya.invoices
            WHERE invoice_date >= '{ps}' AND invoice_date <= '{pe}'
                  AND status != 'void' AND {excl_sql}
            GROUP BY store_name
        """)
        prev_map = {r[0]: r[1] for r in prev}
        print(f"  Prev month: {len(prev)} stores")
    except Exception as e:
        prev_map = {}
        print(f"  Prev month: skipped ({e})")

    # Daily totals
    daily = q(conn, f"""
        SELECT invoice_date, COUNT(*) as bills, ROUND(SUM(total)) as sales
        FROM zakya.invoices
        WHERE invoice_date >= '{start}' AND invoice_date <= '{end}'
              AND status != 'void' AND {excl_sql}
        GROUP BY invoice_date ORDER BY invoice_date
    """)
    print(f"  Days: {len(daily)}")

    # === BUILD REPLACEMENT JS ===
    dn = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    # Stores JS
    slines = []
    for r in rows:
        name, bills, sales, basket = r[0], r[1], r[2], r[3]
        if name not in STORE_MAP: continue
        info = STORE_MAP[name]
        sv = round(sales/100000, 1)
        ly = round(prev_map.get(name, 0)/100000, 1)
        tv = round(sv * 1.15, 1)  # estimated target = actual * 1.15
        s = info["code"].replace("'", "\\'")
        sm = info["sm"].replace("'", "\\'")
        cl = info["cl"]
        slines.append(f"{{s:'{s}',sm:'{sm}',cl:'{cl}',tv:{tv},sv:{sv},ly:{ly},bills:{int(bills)},abs:{int(basket)}}}")

    stores_js = "stores: [\n" + ",\n".join(slines) + "\n],"

    # Daily JS
    dates_list = [f"'{d[0].strftime('%b %d')} {dn[d[0].weekday()]}'" for d in daily]
    sales_list = [str(round(d[2]/100000, 1)) for d in daily]
    bills_list = [str(int(d[1])) for d in daily]

    daily_js = "daily:[" + ",".join(sales_list) + "],"
    dates_js = "dailyDates:[" + ",".join(dates_list) + "],"

    # Trend data
    dl = [round(d[2]/100000, 1) for d in daily]
    mean_v = round(statistics.mean(dl), 1) if dl else 0
    sd_v = round(statistics.stdev(dl), 1) if len(dl) > 1 else 0

    td_sales = "sales:[" + ",".join(sales_list) + "],"
    td_bills = "bills:[" + ",".join(bills_list) + "],"
    td_days = "days:[" + ",".join([f"'{d[0].strftime('%b %d')}'" for d in daily]) + "],"
    td_daynames = "dayNames:[" + ",".join([f"'{dn[d[0].weekday()]}'" for d in daily]) + "],"
    td_mean = f"mean:{mean_v},sd:{sd_v},"

    # === READ & REPLACE TEMPLATE ===
    tpl = TEMPLATE_DIR / "dashboard_template.html"
    if not tpl.exists():
        print(f"ERROR: {tpl} not found"); sys.exit(1)

    with open(tpl, "r") as f:
        html = f.read()

    # Replace stores
    html = re.sub(r"stores: \[.*?\],", stores_js, html, count=1, flags=re.DOTALL)

    # Replace daily & dates
    html = re.sub(r"daily:\[[\d.,\s]+\],", daily_js, html, count=1)
    html = re.sub(r"dailyDates:\[.*?\],", dates_js, html, count=1)

    # Replace trend data (TD object)
    html = re.sub(r"sales:\[[\d.,\s]+\],", td_sales, html, count=1)
    html = re.sub(r"bills:\[[\d.,\s]+\],", td_bills, html, count=1)
    html = re.sub(r"mean:[\d.]+,sd:[\d.]+,", td_mean, html, count=1)

    # Replace TD days/dayNames
    html = re.sub(r"days:\['[^]]+\],", td_days, html, count=1)
    html = re.sub(r"dayNames:\['[^]]+\],", td_daynames, html, count=1)

    # Update timestamp
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p IST")
    html = re.sub(r"Last updated: [^<]+", f"Last updated: {now_str}", html)

    # === SAVE ===
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / "index.html"
    with open(out, "w") as f:
        f.write(html)

    total_cr = round(sum(r[2] for r in rows if r[0] in STORE_MAP) / 10000000, 2)
    total_bills = sum(r[1] for r in rows if r[0] in STORE_MAP)

    print(f"\n  Saved: {out} ({len(html)//1024} KB)")
    print(f"  MTD Sales: Rs {total_cr} Cr")
    print(f"  Bills: {total_bills:,}")
    print(f"  Stores: {len(slines)}")
    print(f"  Days: {len(daily)}")
    print("  BUILD COMPLETE")

if __name__ == "__main__":
    main()
