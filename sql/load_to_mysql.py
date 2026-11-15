# Loads the project CSV files into MySQL and creates the views. Run on your own computer.
# 1) Put the CSV files listed below in ONE folder.  2) Edit the 4 settings.  3) Run:  python load_to_mysql.py
# Install once:  pip install pandas sqlalchemy pymysql cryptography
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

# ---------------- settings ----------------
DATA = Path(r"C:\retail_risk\data")        # the folder holding the CSV files
HOST, PORT, USER, PASSWORD = "localhost", 3306, "root", "YOUR_PASSWORD"
DB = "retail_risk"
# ------------------------------------------

# file name -> (table name, columns to rename because they are MySQL words)
FILES = {
    "features_heldout.csv":     ("features_heldout",  {"group": "grp", "end": "quarter_end"}),
    "clean_quarterly.csv":      ("clean_quarterly",   {"end": "quarter_end"}),
    "companies.csv":            ("companies",         {"group": "grp"}),
    "coverage_added_companies.csv": ("coverage_added", {"group": "grp"}),
    "primary.csv":              ("primary_result",    {"leverage": "lev"}),
    "secondary.csv":            ("secondary_result",  {"leverage": "lev", "view": "view_name"}),
    "cuts.csv":                 ("cut_result",        {"leverage": "lev", "cut": "event_cut"}),
    "per_company.csv":          ("company_result",    {"leverage": "lev", "cut": "event_cut", "min": "auc_min", "max": "auc_max"}),
}
DATE_WORDS = ("end", "date", "filed", "as_of")

root = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/", future=True)
with root.begin() as c: c.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB} CHARACTER SET utf8mb4"))
eng = create_engine(f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB}", future=True)

for fn, (table, ren) in FILES.items():
    p = next((q for q in DATA.rglob(fn)), None)
    if p is None: print(f"MISSING  {fn}  (table {table} skipped)"); continue
    df = pd.read_csv(p)
    df = df.rename(columns={a: b for a, b in ren.items() if a in df.columns})
    for col in df.columns:
        low = col.lower()
        if any(w in low for w in DATE_WORDS) and df[col].dtype == object:
            try: df[col] = pd.to_datetime(df[col], errors="raise")
            except Exception: pass
    df.to_sql(table, eng, if_exists="replace", index=False, chunksize=2000)
    with eng.begin() as c:
        for key in ("ticker", "company"):
            if key in df.columns: c.execute(text(f"ALTER TABLE {table} ADD INDEX idx_{table}_{key} ({key}(20))"))
    print(f"loaded   {fn:32s} -> {table:18s} {len(df):6d} rows, {len(df.columns)} columns")

# run log (one row per frozen test run; edit if you ever rerun)
with eng.begin() as c:
    c.execute(text("CREATE TABLE IF NOT EXISTS run_log (id INT AUTO_INCREMENT PRIMARY KEY, run_time VARCHAR(40), what VARCHAR(200), note VARCHAR(400))"))
    if c.execute(text("SELECT COUNT(*) FROM run_log")).scalar() == 0:
        for r in [("2026-11-02 07:38 UTC", "Step 44 frozen test, first run", "protocol v1.3 hash 781fe9b6...c49292, seed 20261102"),
                  ("2026-11-02 08:06 UTC", "Step 44 frozen test, repeat", "same script, seed and data; output identical; no deviation")]:
            c.execute(text("INSERT INTO run_log (run_time, what, note) VALUES (:a, :b, :c)"), dict(a=r[0], b=r[1], c=r[2]))

# views
sql = "\n".join(l for l in (Path(__file__).parent / "views.sql").read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
with eng.begin() as c:
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        try: c.execute(text(stmt))
        except Exception as e: print("VIEW FAILED:", stmt.split("\n")[0][:60], "->", str(e)[:160])

with eng.connect() as c:
    print("\nVERDICT (from the data just loaded):")
    print(pd.read_sql(text("SELECT lev, scored_companies, company_mean_auc, interval_95, companies_above_half, companies_scored, rule_result FROM v_verdict"), c).to_string(index=False))
    print(pd.read_sql(text("SELECT overall FROM v_overall_verdict"), c).to_string(index=False))
    print("\nTables:", [r[0] for r in c.execute(text("SHOW FULL TABLES WHERE Table_type='BASE TABLE'"))])
    print("Views :", [r[0] for r in c.execute(text("SHOW FULL TABLES WHERE Table_type='VIEW'"))])
