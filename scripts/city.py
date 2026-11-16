#!/usr/bin/env python3
"""Momentum Index for cities without an open planning-applications feed (Manchester first).

London uses the GLA Planning London Datahub. Greater Manchester's ten councils don't publish planning
applications as open data, so the development pipeline comes from two other official sources:
  - Brownfield land registers (MHCLG planning.data.gov.uk): sites councils have identified for housing.
    Scored on hectares, which every council publishes (some, e.g. Bolton and Trafford, omit home numbers).
  - HM Land Registry new-build sales: homes actually being delivered and sold.
plus the same official signals as London: ORR station usage, ONS population, Land Registry resale prices.

Writes data/<city>/momentum.json, data/<city>/tiles.json and data/<city>/pts/<x>_<y>.json.
"""
import json, math, shutil, statistics, urllib.parse, urllib.request, datetime as dt, pathlib
import signals as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
RADIUS_KM = 1.72

CITY_AREAS = {
    "manchester": [
        ("City Centre", "Manchester city centre", "Manchester", 53.4794, -2.2440),
        ("Ancoats", "Ancoats & New Islington", "Manchester", 53.4850, -2.2180),
        ("Salford Quays", "Salford Quays & MediaCity", "Salford", 53.4720, -2.2950),
        ("Hulme", "Hulme & Moss Side", "Manchester", 53.4620, -2.2480),
        ("Cheetham Hill", "Cheetham Hill & Strangeways", "Manchester", 53.5030, -2.2380),
        ("Eastlands", "Eastlands & Openshaw", "Manchester", 53.4820, -2.1800),
        ("Chorlton", "Chorlton", "Manchester", 53.4420, -2.2770),
        ("Stretford", "Stretford & Old Trafford", "Trafford", 53.4500, -2.3080),
        ("Eccles", "Eccles", "Salford", 53.4830, -2.3340),
        ("Didsbury", "Didsbury & Withington", "Manchester", 53.4170, -2.2310),
        ("Stockport", "Stockport town centre", "Stockport", 53.4083, -2.1494),
        ("Altrincham", "Altrincham", "Trafford", 53.3870, -2.3490),
        ("Sale", "Sale", "Trafford", 53.4250, -2.3220),
        ("Ashton", "Ashton-under-Lyne", "Tameside", 53.4880, -2.0950),
        ("Oldham", "Oldham town centre", "Oldham", 53.5409, -2.1114),
        ("Rochdale", "Rochdale town centre", "Rochdale", 53.6150, -2.1580),
        ("Bury", "Bury town centre", "Bury", 53.5930, -2.2970),
        ("Bolton", "Bolton town centre", "Bolton", 53.5780, -2.4290),
        ("Wigan", "Wigan town centre", "Wigan", 53.5450, -2.6320),
    ],
}
WEIGHTS = {"brownfield": 0.25, "newbuild": 0.20, "transport": 0.15, "population": 0.20, "prices": 0.20}
LABELS = {"brownfield": "Brownfield Pipeline", "newbuild": "New-build Delivery", "transport": "Transport Demand",
          "population": "Population Growth", "prices": "Price Momentum"}
SOURCES = {"brownfield": "MHCLG brownfield land registers (planning.data.gov.uk)",
           "newbuild": "HM Land Registry Price Paid Data (new-build sales); OS Code-Point Open",
           "transport": "ORR Estimates of Station Usage; DfT NaPTAN",
           "population": "ONS small-area population estimates (Nomis); ONS Open Geography",
           "prices": "HM Land Registry Price Paid Data; OS Code-Point Open"}


def brownfield_points():
    """Live brownfield register sites in the city box: (lat, lon, homes, permissioned, row-for-postcode-check)."""
    lat0, lat1, lon0, lon1 = S.LONDON
    poly = f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))"
    out, off, orgs = [], 0, {}
    while True:
        qs = urllib.parse.urlencode({"dataset": "brownfield-land", "geometry_relation": "intersects", "geometry": poly,
                                     "limit": 500, "offset": off})
        d = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://www.planning.data.gov.uk/entity.json?{qs}", headers=S.UA), timeout=120))
        ents = d.get("entities", [])
        for e in ents:
            if e.get("end-date"):
                continue  # removed from the register (built out or withdrawn)
            pt = (e.get("point") or "").replace("POINT (", "").replace(")", "").split()
            if len(pt) != 2:
                continue
            lon, lat = float(pt[0]), float(pt[1])
            if not S.in_london(lat, lon):
                continue
            homes = S.num(e.get("maximum-net-dwellings")) or S.num(e.get("minimum-net-dwellings")) or 0
            perm = (e.get("planning-permission-status") or "").replace("-", " ")
            out.append((lat, lon, homes, 1 if "permissioned" in perm and "not" not in perm else 0,
                        {"org": e.get("organisation-entity"), "ref": e.get("reference") or "", "site": (e.get("site-address") or e.get("name") or "")[:70],
                         "perm": perm or "unknown", "date": e.get("planning-permission-date") or e.get("start-date") or "",
                         "notes": (e.get("notes") or "")[:160], "ha": S.num(e.get("hectares"))}))
        if len(ents) < 500:
            break
        off += 500
    for o in {p[4]["org"] for p in out if p[4]["org"]}:
        try:
            orgs[o] = json.load(urllib.request.urlopen(urllib.request.Request(
                f"https://www.planning.data.gov.uk/entity/{o}.json", headers=S.UA), timeout=60)).get("name", "")
        except Exception:  # noqa: BLE001
            orgs[o] = ""
    for p in out:
        p[4]["lpa"] = orgs.get(p[4]["org"], "")
    return out


def i_ha(p):
    return (p[4]["ha"] or 0) >= 0.1


def pct(v, dist):
    if v is None or not dist:
        return None
    below = sum(1 for d in dist if d < v); same = sum(1 for d in dist if d == v)
    return round(100 * (below + 0.5 * same) / len(dist))


def pc(v):
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.1f}%"


def build(city, today=None):
    today = today or dt.date.today()
    S.configure(city)
    loaded, errors = S.load_all(today)
    try:
        bf = brownfield_points()
    except Exception as e:  # noqa: BLE001
        bf, errors["brownfield"] = [], f"{type(e).__name__}: {e}"
    prices = loaded.get("prices", ([], {}, "prices"))[0]
    newb = [p for p in prices if p[3] == 1 and p[5]]  # new-build sales in the latest 12 months

    # per-tile metrics
    tiles = {}
    def put(key, k, v):
        tiles.setdefault(key, {})[k] = v
    agg_bf = {}
    for p in bf:
        a = agg_bf.setdefault(S.tile(p[0], p[1]), [0, 0, 0, 0.0]); a[0] += p[2]; a[1] += p[2] * p[3]; a[2] += 1; a[3] += p[4]["ha"] or 0
    agg_nb = {}
    for p in newb:
        agg_nb[S.tile(p[0], p[1])] = agg_nb.get(S.tile(p[0], p[1]), 0) + 1
    aggs = {n: S.aggregate(pts, kind) for n, (pts, m, kind) in loaded.items()}
    keys = set(aggs.get("population", {})) | set(agg_bf) | set(aggs.get("prices", {}))
    # only tiles with some population (avoid moorland/airport tiles skewing percentiles)
    keys = {k for k in keys if (aggs.get("population", {}).get(k) or {}).get("n", 0) >= 3}
    dist = {"brownfield": [agg_bf.get(k, [0, 0, 0, 0.0])[3] for k in keys], "newbuild": [agg_nb.get(k, 0) for k in keys]}
    for n in ("transport", "population", "prices"):
        mn = {"transport": 1, "population": 3, "prices": 1}[n]
        dist[n] = [a["growth"] for k, a in aggs.get(n, {}).items() if k in keys and a["growth"] is not None and a["n"] >= mn]
    dist["price_level"] = [a["median"] for k, a in aggs.get("prices", {}).items() if k in keys and a["median"] is not None]

    def score(parts):
        have = {k: w for k, w in WEIGHTS.items() if parts.get(k) is not None}
        return round(sum(parts[k] * w for k, w in have.items()) / sum(have.values())) if have else None

    def measure(lat, lon, r_km=None, tile_key=None):
        if tile_key:
            bfa = agg_bf.get(tile_key, [0, 0, 0, 0.0]); nb = agg_nb.get(tile_key, 0)
            off = {n: aggs.get(n, {}).get(tile_key) for n in ("transport", "population", "prices")}
        else:
            near = S.within(bf, lat, lon, r_km)
            bfa = [sum(p[2] for p in near), sum(p[2] * p[3] for p in near), len(near), sum(p[4]["ha"] or 0 for p in near)]
            nb = len(S.within(newb, lat, lon, r_km))
            off = {n: S.summarise(S.within(pts, lat, lon, r_km), kind) for n, (pts, m, kind) in loaded.items()}
        parts = {"brownfield": pct(bfa[3], dist["brownfield"]), "newbuild": pct(nb, dist["newbuild"])}
        o = {"brownfield_homes": round(bfa[0]), "brownfield_permissioned": round(bfa[1]), "brownfield_sites": bfa[2],
             "brownfield_ha": round(bfa[3], 1), "newbuild_sales": nb}
        for n in ("transport", "population", "prices"):
            a = off.get(n)
            g = a["growth"] if a else None
            parts[n] = pct(g, dist[n]) if g is not None else None
            o[n] = round(g, 4) if g is not None else None
            if n == "prices" and a and a.get("median") is not None:
                o["median_price"] = a["median"]
            if n == "transport" and a:
                o["stations"] = a["n"]
        hd = (100 - pct(o["median_price"], dist["price_level"])) if o.get("median_price") is not None else None
        return parts, o, hd, off

    out = []
    span_t = (loaded.get("transport", (None, {}, None))[1] or {}).get("orr", "")
    span_p = (loaded.get("population", (None, {}, None))[1] or {}).get("years", "")
    for n, full, boro, lat, lon in CITY_AREAS[city]:
        parts, o, hd, raw = measure(lat, lon, RADIUS_KM)
        o["transport_span"], o["population_span"] = span_t, span_p
        sc = score(parts)
        have = {k: v for k, v in parts.items() if v is not None}
        lead = max(have, key=have.get)
        nice = {"brownfield": "brownfield land identified for housing", "newbuild": "new-build homes being sold", "transport": "growth in rail use",
                "population": "population growth", "prices": "house-price momentum"}
        bits = [f"{full} scores highest on {nice[lead]} (top {max(1, 100 - have[lead])}% of Greater Manchester).",
                f"{o['brownfield_sites']} brownfield register sites nearby ({o['brownfield_ha']:,} ha)"
                + (f" could take about {o['brownfield_homes']:,} homes" if o["brownfield_homes"] else "")
                + (f", {o['brownfield_permissioned']:,} of them with planning permission" if o["brownfield_permissioned"] else "") + ".",
                f"{o['newbuild_sales']:,} new-build homes sold in the last 12 months."]
        facts = []
        if o.get("population") is not None:
            facts.append(f"population {pc(o['population'])} ({span_p})")
        if o.get("transport") is not None:
            facts.append(f"rail use {pc(o['transport'])}")
        if o.get("prices") is not None:
            facts.append(f"resale prices {pc(o['prices'])} on a year earlier, median £{o['median_price']:,.0f}")
        if facts:
            bits.append("Official statistics: " + "; ".join(facts) + ".")
        near = sorted(S.within(bf, lat, lon, RADIUS_KM), key=lambda p: (-p[2], -(p[4]["ha"] or 0)))[:5]
        det = {"brownfield": [[p[4]["site"], round(p[2]), p[4]["perm"], p[4]["lpa"], p[4]["ha"]] for p in near]}
        if raw.get("transport"):
            det["transport"] = {"now": round(raw["transport"]["now"]), "before": round(raw["transport"]["before"]), "top": raw["transport"].get("top", [])}
        if raw.get("population"):
            det["population"] = {"now": round(raw["population"]["now"]), "before": round(raw["population"]["before"]), "lsoas": raw["population"]["n"]}
        if raw.get("prices"):
            det["prices"] = {"types": raw["prices"]["types"], "new_build": raw["prices"]["new_build"], "sales": raw["prices"]["sales"]}
        out.append({"n": n, "f": full, "b": boro, "lat": lat, "lon": lon, "s": sc, "c": None, "u": f"{o['brownfield_ha']:,} ha",
                    "x": [parts[k] for k in WEIGHTS], "hd": hd, "off": o, "det": det, "raw": {}, "schemes": [], "t": " ".join(bits)})
    out.sort(key=lambda d: -(d["s"] or 0))

    tile_scores = {}
    for key in keys:
        z, x, y = (int(v) for v in key.split("/"))
        nn = 2 ** z
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / nn)))); lon = (x + 0.5) / nn * 360 - 180
        parts, o, hd, _ = measure(lat, lon, tile_key=key)
        sc = score(parts)
        if sc is not None:
            tile_scores[key] = {"s": sc, "x": [parts[k] for k in WEIGHTS], "hd": hd, "lat": round(lat, 5), "lon": round(lon, 5), "off": o}
    bench = {"brownfield": round(statistics.median(dist["brownfield"]), 1) if dist["brownfield"] else 0,
             "newbuild": statistics.median(dist["newbuild"]) if dist["newbuild"] else 0}
    for k in ("transport", "population", "prices", "price_level"):
        if dist.get(k):
            bench[k] = statistics.median(dist[k])
    meta = {n: m for n, (pts, m, kind) in loaded.items()}
    meta["brownfield"] = {"sites": len(bf), "homes": round(sum(p[2] for p in bf))}
    data = {"city": city, "generated": today.isoformat(), "window_days": 365, "radius_km": RADIUS_KM, "tiles": len(tile_scores),
            "weights": WEIGHTS, "labels": [LABELS[k] for k in WEIGHTS], "keys": list(WEIGHTS), "groups": [[0, "DEVELOPMENT PIPELINE"], [2, "DEMAND & PRICES"]],
            "unit_label": "of brownfield land for housing", "sources": SOURCES, "official": meta, "errors": errors, "bench": bench,
            "source": "MHCLG brownfield registers, HM Land Registry, ORR, ONS", "areas": out}
    return data, tile_scores, bf


def write(city, today=None):
    data, tile_scores, bf = build(city, today)
    d = ROOT / "data" / city
    d.mkdir(parents=True, exist_ok=True)
    pub = dict(data); pub["tracked"] = len(data["areas"]); pub["areas"] = data["areas"][:10]
    (d / "momentum.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1))
    ts = {"city": city, "generated": data["generated"], "radius_km": RADIUS_KM, "labels": data["labels"], "keys": data["keys"],
          "weights": data["weights"], "bench": data["bench"], "groups": data["groups"], "tiles": tile_scores,
          "areas": [{"n": a["n"], "f": a["f"], "lat": a["lat"], "lon": a["lon"]} for a in data["areas"]]}
    (d / "tiles.json").write_text(json.dumps(ts, ensure_ascii=False, separators=(",", ":")))
    pdir = d / "pts"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir()
    by = {}
    for p in bf:
        if p[2] < 1 and not i_ha(p):
            continue
        i = p[4]
        status = "Has permission" if p[3] else ("Permission in principle" if "principle" in i["perm"] else "No permission yet")
        row = [round(p[0], 5), round(p[1], 5), int(p[2]), round(i["ha"] or 0, 2), "bf", status, i["date"][:10], i["ref"], i["lpa"], i["site"],
               i["notes"] or (f"{i['ha']} ha brownfield site" if i["ha"] else "Brownfield register site")]
        _, x, y = S.tile(p[0], p[1]).split("/")
        by.setdefault(f"{x}_{y}", []).append(row)
    for k, v in by.items():
        v.sort(key=lambda r: -r[2])
        (pdir / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    return data, {"tiles": len(tile_scores), "sites": len(bf), "files": len(by)}


if __name__ == "__main__":
    import sys
    data, info = write(sys.argv[1] if len(sys.argv) > 1 else "manchester")
    print(info, data["errors"])
    for a in data["areas"]:
        print(a["s"], a["n"], a["x"], "hd", a["hd"], {k: a["off"].get(k) for k in ("brownfield_homes", "newbuild_sales", "transport", "population", "prices", "median_price")})
