# ===== STEP 25: find the debt components the Step 24 formulas missed (Bon-Ton, Pier 1, Destination Maternity, Gordmans, Aeropostale, PacSun, LL Flooring). NO SCORES. =====
import json, re
import numpy as np, pandas as pd
for nm in ["BASE"]:
    if nm not in globals(): raise NameError("BASE is not defined: run the start-of-session cell first")
HO = BASE / "heldout"
ev = pd.read_csv(HO / "failed_events_checked.csv")
NAMEPAT = re.compile(r"Debt|Borrow|Credit|Notes|Loan|Indebted|Financ|Obligation|RelatedPart|Revolv|Lease|Payable", re.I)
SKIP = re.compile(r"^(AccountsPayable|AccruedLiabilities|IncomeTaxes|Interest|Deferred|PaymentsFor|Proceeds|Repayments|Amortization|Increase|Decrease|Operating|Cash)", re.I)
# (name fragment, period ends to inspect, filing numbers in millions seen in the Step 24 output, used only to mark matches with a star)
JOBS = [
 ("Bon-Ton",        ["2017-10-28", "2017-04-29"], [664.566, 345.302, 7.152, 57.208]),
 ("Pier 1",         ["2019-11-30", "2019-08-31"], [96.0, 2.875]),
 ("Destination",    ["2019-08-03"],               [23.3, 3.841, 21.343]),
 ("Gordmans",       ["2016-10-29", "2015-10-31"], [59.397, 26.074, 37.247, 27.744]),
 ("Aeropostale",    ["2016-04-30", "2016-01-30"], [144.239, 73.468, 5.0, 137.960]),
 ("Pacific Sunwear",["2015-10-31"],               [35.0, 97.023]),
 ("LL Flooring",    ["2024-03-31", "2023-09-30"], []),
]
def show(f_all, end, targets):
    rows = []
    for ns, tags in f_all.items():
        if ns == "dei": continue
        for tag, body in tags.items():
            for u in body.get("units", {}).get("USD", []):
                if "start" in u or abs((pd.Timestamp(u["end"]) - pd.Timestamp(end)).days) > 3: continue
                v = u["val"] / 1e6
                star = any(abs(v - t) <= max(0.0006 * t, 0.0015) for t in targets)
                if star or (NAMEPAT.search(tag) and not SKIP.search(tag)):
                    rows.append((u["filed"], ns, tag, v, star))
    out = pd.DataFrame(rows, columns=["filed", "namespace", "tag", "value_m", "match"]).sort_values(["filed", "value_m"], ascending=[True, False]).drop_duplicates(["namespace", "tag", "value_m"])
    return out
for frag, dates, targets in JOBS:
    m = ev[ev["name"].str.contains(frag, regex=False)]
    if m.empty: print("not found:", frag); continue
    cik = int(m.iloc[0]["cik"]); f_all = json.load(open(HO / "raw" / f"{cik:010d}.json"))["facts"]
    print("\n" + "=" * 100 + f"\n{m.iloc[0]['name']}: namespaces in the file: {list(f_all.keys())}")
    for d in dates:
        t = show(f_all, d, targets)
        print(f"\n  period end {d}: balance-sheet facts with debt-like names, or equal to a number seen in the filing (* = matches a filing number)")
        print("   " + t.assign(match=t["match"].map({True: "*", False: ""})).to_string(index=False).replace("\n", "\n   ") if len(t) else "   none")
print("\nHow to read this: a '*' tag is the XBRL fact for a line we saw in the filing. Tell me which ones form the total debt for each company; I will write the corrected formula.")
