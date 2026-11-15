# ===== STEP 11: decide the COVID window from the data, clean the delay artifact, recount usable history =====
F = pd.read_csv(BASE / "features_relative.csv", parse_dates=["end", "distress_date", "as_of_date"])
RAW3 = ["gm_chg_yoy", "inv_gap", "ocf_margin"]

# 1) how spread out are the 20 companies in each calendar quarter? (median absolute deviation, raw signals, all groups)
def mad(x):
    x = x.dropna(); return (x - x.median()).abs().median() if len(x) >= 6 else np.nan
D = F.groupby("cal_q")[RAW3].agg(mad)
D["n"] = F.groupby("cal_q")["gm_chg_yoy"].count()
quiet = D.loc["2022Q4":"2025Q4", RAW3]
base = quiet.median()
D["signals_above_2x"] = (D[RAW3] > 2 * base).sum(axis=1)
D["covid_window"] = D["signals_above_2x"] >= 2
print("CHECK 1: spread of the raw signals across companies, by calendar quarter (quiet baseline = 2022Q4 to 2025Q4)")
print("baseline spread:", base.round(2).to_dict())
print(D.round(2).to_string(), "\n")
win = list(D.index[D["covid_window"]])
print("CHECK 2: quarters flagged as shock quarters by the data:", win)
print("          (my own guess before looking was 2020Q2 to 2021Q3)\n")
F["covid_window"] = F["cal_q"].isin(win)

# 2) filing delay: a value first filed more than 100 days after quarter end is not an original report
#    (largest normal delay seen: 93 days). Those are comparatives picked up from later filings.
F["delay_prev"] = F["delay_days"] - F["delay_chg_yoy"]
art = (F["delay_days"] > 100) | (F["delay_prev"] > 100)
print("CHECK 3: rows whose filing delay is not an original filing (delay_days > 100, or the prior-year one was)")
print(F[art][["ticker", "group", "end", "delay_days", "delay_prev", "delay_chg_yoy"]].round({"delay_days": 0, "delay_prev": 0, "delay_chg_yoy": 0}).to_string(index=False), "\n")
F["delay_artifact"] = art
F["delay_chg_clean"] = np.where(art, np.nan, F["delay_chg_yoy"])
F["delay_chg_rel_clean"] = np.where(art, np.nan, F["delay_chg_yoy_rel"])

# 3) cleaned signals: peer-adjusted, blank inside the shock window
SIGS = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "ocf_margin", "cr_chg_yoy"]
for s in SIGS:
    F[s + "_clean"] = np.where(F["covid_window"], np.nan, F[s + "_rel"])
F["delay_chg_clean_w"] = np.where(F["covid_window"], np.nan, F["delay_chg_rel_clean"])
F.drop(columns=["delay_prev"]).to_csv(BASE / "features_final.csv", index=False)
print("saved features_final.csv:", len(F), "rows\n")

# 4) usable history for failed companies: last 8 quarters before distress
H123 = ["gm_chg_yoy_clean", "inv_gap_clean", "lev_chg_yoy_clean"]
fl = F[(F.group == "failed") & (F.qtd <= 8)].copy()
fl["h123_full"] = fl[H123].notna().all(axis=1)
fl["h4_ok"] = fl["delay_chg_clean_w"].notna()
fl["in_window"] = fl["covid_window"]
print("CHECK 4: failed companies, last 8 quarters before distress")
print(fl.groupby("ticker").agg(quarters=("end", "size"), in_shock_window=("in_window", "sum"), H1_H3_full=("h123_full", "sum"),
      gm=("gm_chg_yoy_clean", "count"), inv=("inv_gap_clean", "count"), lev=("lev_chg_yoy_clean", "count"), H4_delay=("h4_ok", "sum")).to_string(), "\n")
print("same count, but WITHOUT blanking the shock window (peer-adjusted only), for comparison:")
fl["h123_raw"] = fl[["gm_chg_yoy_rel", "inv_gap_rel", "lev_chg_yoy_rel"]].notna().all(axis=1)
print(fl.groupby("ticker")["h123_raw"].sum().to_string(), "\n")

print("CHECK 5: most extreme cleaned values (the COVID extremes should be gone)")
for s in [x + "_clean" for x in SIGS] + ["delay_chg_clean_w"]:
    x = F.dropna(subset=[s]).reindex(F[s].abs().dropna().sort_values(ascending=False).index).head(3)
    print(s, "->", [(a, str(b.date()), round(c, 2)) for a, b, c in zip(x.ticker, x.end, x[s])])
