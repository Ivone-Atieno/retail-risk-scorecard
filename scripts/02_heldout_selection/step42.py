# ===== STEP 42: rebuild your Step 2 (date merge) from its written description and PROVE it against the clean_02_dates.csv you already have. NO SCORES. =====
# Run in the Colab session where BASE is defined. Read-only: it writes nothing except step42_check.csv (a small diff list). Takes under a minute.
import pandas as pd, numpy as np
for nm in ["BASE"]:
    if nm not in globals(): raise NameError("BASE is not defined: run the start-of-session cell first")
L = pd.read_csv(BASE / "clean_01_long.csv", parse_dates=["start", "end", "filed"])
T = pd.read_csv(BASE / "clean_02_dates.csv", parse_dates=["start", "end", "filed", "end_raw"])
print("clean_01_long rows:", len(L), "| clean_02_dates rows:", len(T), "| columns in clean_02:", [c for c in T.columns if c not in L.columns])

def merge_dates(df, window):
    """Per company, period-end dates that are within `window` days of each other are one date: keep the date with more rows (tie: the later date). end_raw keeps the original."""
    df = df.copy(); df["end_raw"] = df["end"]; mp = {}
    for tk, g in df.groupby("ticker"):
        cnt = g["end"].value_counts().sort_index(); ds = list(cnt.index); grp = [[ds[0]]] if ds else []
        for d in ds[1:]:
            (grp[-1].append(d) if (d - grp[-1][-1]).days <= window else grp.append([d]))
        for gr in grp:
            if len(gr) > 1:
                keep = max(gr, key=lambda d: (cnt[d], d))
                for d in gr: mp[(tk, d)] = keep
    df["end"] = [mp.get((t, e), e) for t, e in zip(df["ticker"], df["end"])]
    return df, mp

key = ["ticker", "metric", "tag", "start", "filed", "end_raw", "val"]
res = []
for w in (1, 2, 3, 4):
    M, mp = merge_dates(L, w)
    j = M[key + ["end"]].merge(T[key + ["end"]], on=key, how="outer", suffixes=("_mine", "_yours"), indicator=True)
    both = j[j["_merge"] == "both"]
    res.append(dict(window_days=w, groups_merged=len({(t, k) for (t, d), k in mp.items() if d != k}), rows_changed_mine=int((M["end"] != M["end_raw"]).sum()),
                    rows_changed_yours=int((T["end"] != T["end_raw"]).sum()), unmatched_rows=int((j["_merge"] != "both").sum()),
                    end_differs=int((both["end_mine"] != both["end_yours"]).sum())))
R = pd.DataFrame(res); print(R.to_string(index=False))
ok = R[(R.unmatched_rows == 0) & (R.end_differs == 0)]
print("\nVERDICT:", f"my rebuild reproduces your Step 2 exactly with a window of {int(ok.window_days.min())} day(s)." if len(ok) else "NO window reproduces your file exactly: paste this table and the diff file; I will not guess further.")
w = int(ok.window_days.min()) if len(ok) else 2
M, mp = merge_dates(L, w)
x = M[["ticker", "metric", "tag", "ptype", "end", "end_raw", "val", "filed"]].merge(T[["ticker", "metric", "tag", "ptype", "end", "end_raw", "val", "filed"]], on=["ticker", "metric", "tag", "ptype", "end_raw", "val", "filed"], how="outer", suffixes=("_mine", "_yours"))
d = x[(x["end_mine"] != x["end_yours"]) | x["end_mine"].isna() | x["end_yours"].isna()]
d.to_csv(BASE / "step42_check.csv", index=False); print("differing rows saved to step42_check.csv:", len(d)); print(d.head(15).to_string(index=False))
print("\nmerged date groups (company: dropped date -> kept date):", {f"{t} {str(a.date())}": str(k.date()) for (t, a), k in mp.items() if a != k})
