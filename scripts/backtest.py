#!/usr/bin/env python3
"""Back-test: did areas with high planning momentum go on to outperform on house prices?

For each start date T0 we rebuild the planning half of the Momentum Index exactly as the live index does
(4 planning signals, 12 months of GLA Planning London Datahub filings to T0, percentiles across London's
zoom-13 map tiles, live weights re-scaled to the planning signals). We then measure each tile's resale
price change from the 12 months to T0 to the latest 12 months (HM Land Registry, resales only, like-for-like
by property type) and compare score bands. Only the planning signals can be rebuilt historically.

  python3 scripts/backtest.py      -> data/backtest.json
"""
import csv, json, math, statistics, datetime as dt, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import momentum as M
import signals as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"


def sales(years):
    pcs = S.postcode_points()
    out = []
    for y in years:
        f = S.fetch(f"{BASE}/pp-{y}.csv", f"pp-{y}.csv", 7 if y >= dt.date.today().year else 365)
        for r in csv.reader(open(f, encoding="latin-1")):
            if len(r) < 15 or r[13] != "GREATER LONDON" or r[14] != "A" or r[4] == "O" or r[5] == "Y":
                continue  # London, standard sales, no 'other' type, resales only
            loc = pcs.get(r[3].replace(" ", ""))
            if loc:
                out.append((S.tile(*loc), dt.date.fromisoformat(r[2][:10]), r[4], float(r[1])))
    return out


def growth(rows, a0, a1, b0, b1):
    """Mix-adjusted median change per tile between window A and window B."""
    by = {}
    for t, d, typ, p in rows:
        w = 0 if a0 < d <= a1 else 1 if b0 < d <= b1 else None
        if w is not None:
            by.setdefault(t, {}).setdefault(typ, ([], []))[w].append(p)
    out = {}
    for t, types in by.items():
        num = den = 0
        for typ, (a, b) in types.items():
            if len(a) >= 10 and len(b) >= 10:
                num += len(b) * (statistics.median(b) / statistics.median(a) - 1); den += len(b)
        if den >= 40:
            out[t] = num / den
    return out


def london_growth(rows, a0, a1, b0, b1):
    return growth([("L", d, typ, p) for _, d, typ, p in rows], a0, a1, b0, b1).get("L")


def spearman(x, y):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for k, i in enumerate(o):
            r[i] = k
        return r
    rx, ry = rank(x), rank(y); n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return cov / math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))


def run(t0, rows, end):
    keyed = M.tiles(t0, keyed=True)
    dist = list(keyed.values())
    w = M.PLAN_W; tot = sum(w.values())
    scores = {k: round(sum(M.pct(sig[s], [d[s] for d in dist]) * w[s] for s in w) / tot) for k, sig in keyed.items()}
    a0, a1 = t0 - dt.timedelta(days=365), t0
    b0, b1 = end - dt.timedelta(days=365), end
    g = growth(rows, a0, a1, b0, b1)
    lon = london_growth(rows, a0, a1, b0, b1)
    common = [k for k in scores if k in g]
    xs = [scores[k] for k in common]; ys = [g[k] for k in common]
    bands = []
    for lo, hi, name in ((80, 101, "80–100"), (60, 80, "60–79"), (40, 60, "40–59"), (0, 40, "0–39")):
        v = [g[k] for k in common if lo <= scores[k] < hi]
        if v:
            bands.append({"band": name, "areas": len(v), "median_growth": round(statistics.median(v), 4),
                          "vs_london_pts": round((statistics.median(v) - lon) * 100, 1),
                          "beat_london": round(sum(1 for x in v if x > lon) / len(v), 3)})
    return {"start": t0.isoformat(), "end": end.isoformat(), "areas": len(common), "london_growth": round(lon, 4),
            "spearman": round(spearman(xs, ys), 3), "bands": bands}


def population_test(t0):
    """Planning score at t0 vs ONS small-area population change (mid-2021 to latest mid-year)."""
    S.configure("london"); pts, meta = S.population_points(); agg = S.aggregate(pts, "population")
    keyed = M.tiles(t0, keyed=True); dist = list(keyed.values()); w = M.PLAN_W; tot = sum(w.values())
    sc = {k: sum(M.pct(s[x], [d[x] for d in dist]) * w[x] for x in w) / tot for k, s in keyed.items()}
    ks = [k for k in sc if k in agg and agg[k]["n"] >= 3 and agg[k]["growth"] is not None]
    lon = sum(agg[k]["now"] for k in ks) / sum(agg[k]["before"] for k in ks) - 1
    bands = []
    for lo, hi, name in ((80, 101, "80–100"), (60, 80, "60–79"), (40, 60, "40–59"), (0, 40, "0–39")):
        v = [agg[k]["growth"] for k in ks if lo <= sc[k] < hi]
        if v:
            bands.append({"band": name, "areas": len(v), "median_growth": round(statistics.median(v), 4),
                          "beat_london": round(sum(1 for x in v if x > lon) / len(v), 3)})
    return {"start": t0.isoformat(), "years": meta["years"], "areas": len(ks), "london_growth": round(lon, 4),
            "spearman": round(spearman([sc[k] for k in ks], [agg[k]["growth"] for k in ks]), 3), "bands": bands}


def headroom_test(rows, t0, end):
    """Resale price change by starting price level (thirds of London areas): does cheaper outperform?"""
    a0, a1 = t0 - dt.timedelta(days=365), t0
    g = growth(rows, a0, a1, end - dt.timedelta(days=365), end)
    lvl = {}
    for t, d, typ, p in rows:
        if a0 < d <= a1:
            lvl.setdefault(t, []).append(p)
    lvl = {k: statistics.median(v) for k, v in lvl.items() if len(v) >= 40 and k in g}
    ks = sorted(lvl, key=lvl.get); n = len(ks)
    thirds = [ks[: n // 3], ks[n // 3: 2 * n // 3], ks[2 * n // 3:]]
    return {"start": t0.isoformat(), "end": end.isoformat(), "areas": n,
            "spearman_price_level": round(spearman([lvl[k] for k in ks], [g[k] for k in ks]), 3),
            "thirds": [{"group": name, "median_growth": round(statistics.median([g[k] for k in grp]), 4)}
                       for name, grp in zip(("cheapest", "middle", "priciest"), thirds)]}


def main():
    rows = sales(range(2020, dt.date.today().year + 1))
    end = max(d for _, d, _, _ in rows)
    res = [run(dt.date(2021, 9, 30), rows, end), run(dt.date(2022, 9, 30), rows, end)]
    pop = population_test(dt.date(2021, 6, 30))
    hr = [headroom_test(rows, dt.date(2021, 9, 30), end), headroom_test(rows, dt.date(2022, 9, 30), end)]
    out = {"generated": dt.date.today().isoformat(), "method": __doc__.strip(), "price_tests": res, "population_test": pop,
           "headroom_tests": hr}
    print("headroom:", hr)
    print("population:", pop)
    (ROOT / "data" / "backtest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for r in res:
        print(r["start"], "→", r["end"], "areas", r["areas"], "London", r["london_growth"], "rho", r["spearman"])
        for b in r["bands"]:
            print("   ", b)


if __name__ == "__main__":
    main()
