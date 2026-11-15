# ===== STEP 9b: look at the odd values before using them (diagnostics only, nothing is changed or saved) =====
F = pd.read_csv(BASE / "features_quarterly.csv", parse_dates=["end", "distress_date", "as_of_date"])
pd.set_option("display.width", 200)
def r2(d): return d.round({c: 2 for c in d.columns if pd.api.types.is_float_dtype(d[c])})

print("A) filing delay: days from quarter end to the first filing that carried the balance sheet")
print(F.groupby("group")["delay_days"].describe(percentiles=[.05, .5, .95]).round(0).to_string())
odd = F[(F["delay_days"] > 100) | (F["delay_days"] < 15)]
print("\nrows with delay > 100 or < 15 days:", len(odd), "of", F["delay_days"].notna().sum())
print(odd[["ticker", "end", "delay_days"]].sort_values("delay_days").head(25).to_string(index=False))
big = F[F["delay_chg_yoy"].abs() > 60][["ticker", "end", "delay_days", "delay_chg_yoy"]]
print("\nrows with a year-on-year delay change over 60 days:", len(big))
print(big.sort_values("delay_chg_yoy").head(15).to_string(index=False), "\n")

print("B) COVID base effect: the biggest margin and inventory moves, in context")
cols = ["ticker", "end", "gross_margin", "gm_chg_yoy", "rev_yoy", "inv_gap"]
for tk in ["PLCE", "EXPR", "ROST"]:
    x = r2(F[(F.ticker == tk) & (F.end >= "2020-02-01") & (F.end <= "2021-09-01")][cols])
    print(x.to_string(index=False), "\n")

print("C) leverage: BBBY and BIG in their last usable quarters, plus the healthy group around the March 2020 borrowing")
print(r2(F[(F.ticker == "BBBY (old)") & (F.qtd <= 6)][["ticker", "end", "qtd", "debt_to_ca", "lev_chg_yoy"]]).to_string(index=False), "\n")
print(r2(F[(F.ticker == "BIG") & (F.end >= "2021-12-01") & (F.end <= "2023-10-31")][["ticker", "end", "qtd", "debt_to_ca", "lev_chg_yoy"]]).to_string(index=False), "\n")
h = r2(F[(F.group == "healthy") & (F.end >= "2020-04-01") & (F.end <= "2020-08-15")][["ticker", "end", "debt_to_ca", "lev_chg_yoy"]])
print(h.to_string(index=False), "\n")

print("D) negative-equity rows by company and group")
print(F[F.equity_negative].groupby(["group", "ticker"]).size().to_string())
