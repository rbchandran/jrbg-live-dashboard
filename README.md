# JRBG MTD Dashboard · Auto-Refresh via GitHub Pages

## Architecture

```
SAP / Zoho POS (Daily transactions)
       ↓
Data Warehouse (MotherDuck)
       ↓
GitHub Actions (SQL query at 7 AM IST)
       ↓
Latest data fetched automatically
       ↓
Dashboard HTML rebuilt (build_dashboard.py)
       ↓
GitHub Pages updated (same URL, fresh data)
```

**Cost: ₹0/month. Fully automated. Zero manual effort after setup.**

---

## One-Time Setup (30 minutes)

### 1. Create GitHub Repo
```bash
# Create new repo: jrbg-dashboard (Private)
git init
git add .
git commit -m "🚀 Initial setup"
git remote add origin https://github.com/YOUR_ORG/jrbg-dashboard.git
git push -u origin main
```

### 2. Enable GitHub Pages
- Go to repo **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: **main** → folder: **/docs**
- Click Save
- Your URL: `https://YOUR_ORG.github.io/jrbg-dashboard/`

### 3. Add MotherDuck Token
- Go to repo **Settings → Secrets → Actions**
- New secret: `MOTHERDUCK_TOKEN`
- Value: your token from [app.motherduck.com](https://app.motherduck.com) → Settings → API Tokens

### 4. First Build
- Go to **Actions** tab → **JRBG Daily Dashboard** → **Run workflow**
- Select region: KL, TN, or ALL
- Watch it run (~2 minutes)
- Check your GitHub Pages URL — dashboard is live!

### 5. Share the Link
```
https://YOUR_ORG.github.io/jrbg-dashboard/
```
Share with Allen, Cluster Heads, anyone. No login required. Works on phone.

---

## Daily Operation

| Time | What Happens |
|------|-------------|
| 06:00 AM | POS data syncs to MotherDuck |
| 07:00 AM | GitHub Actions triggers automatically |
| 07:02 AM | Python queries MotherDuck (stores, daily, LOB) |
| 07:03 AM | Fresh HTML built with real data |
| 07:04 AM | Committed to repo → GitHub Pages deploys |
| 08:00 AM | Anyone opens the link → sees latest data |

**Nothing to do. It runs every day forever.**

---

## Multi-Region Support

```bash
# KL only (default)
python build_dashboard.py --region KL

# Chennai/TN only
python build_dashboard.py --region TN

# Both regions (creates separate pages)
python build_dashboard.py --region ALL
```

When `ALL`: creates `dashboard_kl.html` and `dashboard_tn.html` with a switcher page.

---

## File Structure

```
jrbg-dashboard/
├── .github/workflows/
│   └── daily-dashboard.yml      ← Cron: 7 AM IST daily
├── assets/
│   └── logo.jpeg                ← Ramachandran logo
├── docs/                        ← GitHub Pages serves this folder
│   ├── .nojekyll                ← Tells GitHub to serve raw HTML
│   └── index.html               ← The live dashboard (auto-rebuilt daily)
├── templates/
│   └── dashboard_template.html  ← 9-tab dashboard layout
├── build_dashboard.py           ← Main build script
├── requirements.txt             ← Python deps
└── README.md                    ← This file
```

---

## Adding a New Region

1. Add entry to `REGIONS` dict in `build_dashboard.py`:
```python
"NEW_REGION": {
    "name": "New Region",
    "pos": "Zakya",  # or "Gofrugal"
    "invoice_table": "my_db.new_schema.invoices",
    ...
}
```
2. Add the region to the workflow dropdown
3. Push → dashboard auto-builds for new region

---

## Monitoring & Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails | Check Actions tab → read error logs |
| Auth error | Refresh MotherDuck token in repo secrets |
| Stale data | Check if POS sync ran (MotherDuck → bronze tables) |
| Page not updating | Check Settings → Pages is enabled on `main` `/docs` |
| New store appears | Automatic — script discovers stores from data |
| SM/CH changed | Update store_managers / category_heads mapping |

---

## Security

- Repo is **private** — code not visible to public
- GitHub Pages URL is **public** (anyone with link can view)
- To restrict: use GitHub Pages with access control (GitHub Enterprise)
- No credentials in code — all in GitHub Secrets
- MotherDuck token has read-only scope
