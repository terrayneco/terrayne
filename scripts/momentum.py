#!/usr/bin/env python3
"""Terrayne Development Momentum Index, built from live GLA Planning London Datahub data.

Run:  python3 scripts/momentum.py            -> writes data/momentum.json
      python3 scripts/momentum.py --html F    -> also refreshes the snapshot embedded in F

Method (shown on the site as well):
  Each tracked neighbourhood is a circle of radius 1.72 km (9.3 km2) around a fixed point.
  Seven signals, four from planning applications (GLA Planning London Datahub, last 12 months)
  and three from other official statistics (see scripts/signals.py):
    1. Planning Activity     number of non-householder, non-minor applications            15%
    2. Development Pipeline  net new homes proposed (live or approved schemes)            20%
    3. Class MA conversions  homes proposed via office-to-residential prior approvals     10%
    4. Commercial Floorspace net non-residential floorspace (m2) proposed                 10%
    5. Transport demand      growth in station entries+exits (TfL counts, ORR usage)      15%
    6. Population growth     ONS small-area mid-year estimates                            15%
    7. Price momentum        median sale price vs a year earlier (HM Land Registry)       15%
  Each signal becomes a percentile (0-100) against every 9.3 km2 map tile in Greater London
  (zoom-13 web-map tiles, the same area as the circles). The Index is the weighted average of
  the signals available for that neighbourhood (weights re-scaled if one is missing).
  Price headroom (shown alongside, not in the score) = how cheap the median sale is vs London.
  The 30-day change is today's Index minus the Index with planning data for the 12 months
  ending 30 days ago (the official statistics update monthly to yearly).
No API key needed: uses the Datahub's public guest endpoint. Standard library only.
"""
import json, sys, datetime as dt, urllib.request, pathlib, re, math

API = "https://planningdata.london.gov.uk/api-guest/applications/_search"
HEAD = {"Content-Type": "application/json", "X-API-AllowRequest": "be2rmRnt&"}
RADIUS_KM = 1.72
TILE_ZOOM = 13
BBOX = {"top_left": {"lat": 51.70, "lon": -0.52}, "bottom_right": {"lat": 51.28, "lon": 0.34}}
PLAN_W = {"act": 0.15, "pipe": 0.20, "ma": 0.10, "com": 0.10}
OFFICIAL_W = {"transport": 0.15, "population": 0.15, "prices": 0.15}
WEIGHTS = {**PLAN_W, **OFFICIAL_W}
LABELS = {"act": "Planning Activity", "pipe": "Development Pipeline", "ma": "Class MA (Office-to-Resi)", "com": "Commercial Floorspace",
          "transport": "Transport Demand", "population": "Population Growth", "prices": "Price Momentum"}
SOURCES = {"act": "GLA Planning London Datahub", "pipe": "GLA Planning London Datahub", "ma": "GLA Planning London Datahub",
           "com": "GLA Planning London Datahub", "transport": "TfL Annual Station Counts; ORR Estimates of Station Usage; DfT NaPTAN",
           "population": "ONS small-area population estimates (Nomis); ONS Open Geography", "prices": "HM Land Registry Price Paid Data; OS Code-Point Open"}

# Tracked submarkets: name, full name, boroughs, centre lat, lon
AREAS = [
    ("Nine Elms", "Nine Elms & Vauxhall", "LB Wandsworth / Lambeth", 51.4815, -0.1290),
    ("Stratford", "Stratford & Olympic Park", "LB Newham", 51.5416, -0.0034),
    ("Canada Water", "Canada Water & Surrey Quays", "LB Southwark", 51.4980, -0.0497),
    ("Whitechapel", "Whitechapel & Aldgate", "LB Tower Hamlets", 51.5195, -0.0597),
    ("King’s Cross", "King’s Cross & St Pancras", "LB Camden / Islington", 51.5347, -0.1246),
    ("Croydon", "Croydon town centre", "LB Croydon", 51.3762, -0.0982),
    ("Old Kent Road", "Old Kent Road", "LB Southwark", 51.4850, -0.0750),
    ("Elephant", "Elephant & Castle", "LB Southwark / Lambeth", 51.4945, -0.1000),
    ("Wembley", "Wembley Park", "LB Brent", 51.5600, -0.2795),
    ("Brent Cross", "Brent Cross & Cricklewood", "LB Barnet", 51.5700, -0.2200),
    ("Tottenham Hale", "Tottenham Hale", "LB Haringey", 51.5880, -0.0600),
    ("Ilford", "Ilford town centre", "LB Redbridge", 51.5590, 0.0700),
    ("Greenwich Pen.", "Greenwich Peninsula", "RB Greenwich", 51.4990, 0.0050),
    ("Woolwich", "Woolwich", "RB Greenwich", 51.4910, 0.0690),
    ("Lewisham", "Lewisham town centre", "LB Lewisham", 51.4620, -0.0120),
    ("Hammersmith", "Hammersmith & White City", "LB Hammersmith & Fulham", 51.5000, -0.2250),
    ("Ealing", "Ealing Broadway", "LB Ealing", 51.5130, -0.3010),
    ("Isle of Dogs", "Canary Wharf & Isle of Dogs", "LB Tower Hamlets", 51.5000, -0.0180),
]

RES = "application_details.residential_details."
PROP, EXIST = RES + "total_no_proposed_residential_units", RES + "total_no_existing_residential_units"
GAIN = "application_details.non_residential_details.total_gia_gained"
LOST = "application_details.non_residential_details.total_gia_lost"
CLASS_MA = "Prior Approval: Change of use from Commercial, Business and Service (Use Class E) to Dwellinghouses (Use Class C3)"
MINOR_TYPES = [
    "Householder planning permission", "Approval of details reserved by a condition (discharge)",
    "Lawful development: Proposed use", "Lawful development: Existing use",
    "Tree works: Trees in conservation areas/subject to TPOs", "Prior Approval: Larger Home Extension",
    "Non-Material Amendment", "Consent to display an advertisement", "Listed building consent",
    "Householder planning & demolition in a conservation area", "Householder planning & listed building consent",
    "Prior Approval: Development for electronic communications network",
    "Prior Approval: Roof mounted solar PV on non-domestic building",
    "Householder: Enlargement of a dwellinghouse by construction of additional storeys",
]
MINOR_PHRASES = ["discharge of condition", "details pursuant to condition", "non-material amendment",
                 "certificate of lawful", "lawful development certificate", "advertisement consent",
                 "tree preservation order", "works to tree", "telecommunications", "electronic communications code"]
DUPLICATE_TYPES = ["Removal/Variation of a condition", "Approval of reserved matters", "Non-Material Amendment",
                   "Approval of details reserved by a condition (discharge)"]
DEAD = ["Refused", "REFUSED", "Withdrawn", "Lapsed", "Not Required", "Appeal Dismissed"]


def q(body):
    req = urllib.request.Request(API, json.dumps(body).encode(), HEAD)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def window(end):
    f = lambda d: d.strftime("%d/%m/%Y")
    return {"range": {"valid_date": {"gte": f(end - dt.timedelta(days=365)), "lte": f(end), "format": "dd/MM/yyyy"}}}


def terms(field, vals):
    return {"terms": {field + ".raw": vals}}


QUALIFYING = {"bool": {"must_not": [{"term": {"application_type.raw": "Householder"}}, terms("application_type_full", MINOR_TYPES)]
                       + [{"match_phrase": {"description": p}} for p in MINOR_PHRASES]}}
UNIT_ELIGIBLE = {"bool": {"must_not": [terms("application_type_full", DUPLICATE_TYPES), terms("status", DEAD),
                                        {"match_phrase": {"description": "variation of condition"}},
                                        {"match_phrase": {"description": "section 73"}}]}}
CLASS_MA_Q = {"bool": {"should": [{"term": {"application_type_full.raw": CLASS_MA}},
                                  {"match_phrase": {"description": "class ma"}}], "minimum_should_match": 1,
                       "must_not": [terms("status", DEAD)]}}

SIGNAL_AGGS = {
    "act": {"filter": QUALIFYING},
    "pipe": {"filter": UNIT_ELIGIBLE, "aggs": {"p": {"sum": {"field": PROP}}, "e": {"sum": {"field": EXIST}}}},
    "ma": {"filter": CLASS_MA_Q, "aggs": {"p": {"sum": {"field": PROP}}}},
    "com": {"filter": {"bool": {"filter": [QUALIFYING, UNIT_ELIGIBLE]}},
            "aggs": {"g": {"sum": {"field": GAIN}}, "l": {"sum": {"field": LOST}}}},
}


def signals(b):
    return {"act": b["act"]["doc_count"],
            "pipe": max(0, b["pipe"]["p"]["value"] - b["pipe"]["e"]["value"]),
            "ma": b["ma"]["p"]["value"] + 0.5 * b["ma"]["doc_count"],  # units, tiny bonus per filing so 0-unit records still count
            "com": max(0, b["com"]["g"]["value"] - b["com"]["l"]["value"])}


def tiles(end):
    body = {"size": 0, "query": {"bool": {"filter": [window(end), {"geo_bounding_box": {"centroid": BBOX}}]}},
            "aggs": {"t": {"geotile_grid": {"field": "centroid", "precision": TILE_ZOOM, "size": 2000}, "aggs": SIGNAL_AGGS}}}
    return [signals(b) for b in q(body)["aggregations"]["t"]["buckets"] if b["doc_count"] >= 5]


def area_query(lat, lon, end, top=0):
    geo = {"geo_distance": {"distance": f"{RADIUS_KM}km", "centroid": {"lat": lat, "lon": lon}}}
    body = {"size": top, "query": {"bool": {"filter": [window(end), geo]}}, "aggs": SIGNAL_AGGS}
    if top:
        body["query"]["bool"]["filter"].append(UNIT_ELIGIBLE)
        body["sort"] = [{PROP: {"order": "desc", "missing": "_last"}}]
        body["_source"] = ["lpa_app_no", "lpa_name", "site_name", "street_name", "description", "status",
                           "valid_date", "application_type_full", "centroid", PROP, EXIST]
    return q(body)


def pct(v, dist):
    below = sum(1 for d in dist if d < v); same = sum(1 for d in dist if d == v)
    return round(100 * (below + 0.5 * same) / len(dist)) if dist else 0


def score(sig, dist, extra=None):
    parts = {k: pct(sig[k], [d[k] for d in dist]) for k in PLAN_W}
    parts.update(extra or {})
    have = {k: w for k, w in WEIGHTS.items() if parts.get(k) is not None}
    return round(sum(parts[k] * w for k, w in have.items()) / sum(have.values())), parts


def km(a, b, c, d):
    return math.hypot((d - b) * 69.4, (c - a) * 111.2)


def nearest(lat, lon):
    return min(AREAS, key=lambda a: km(lat, lon, a[3], a[4]))[0]


def homes(n):
    return f"{fnum(n)} home" + ("" if round(n) == 1 else "s")


def fnum(n):
    return f"{int(round(n)):,}"


def tidy(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def label(site, street):
    site, street = tidy(site), tidy(street)
    if street and street.lower() not in site.lower() and (len(site) < 14 or site.lower().endswith((" to", " at", " and"))
                                                          or re.search(r"\d$", site)):
        site = f"{site} {street}".strip()
    site = re.sub(r",?\s*London\b.*$", "", site, flags=re.I)
    site = re.sub(r",?\s*[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", "", site).strip(" ,")
    if site == site.lower() or site == site.upper():
        site = " ".join(w.capitalize() for w in site.split())
    return site or street


def pc(v):
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.1f}%"


def takeaway(full, sig, parts, schemes, off=None):
    bits = []
    have = {k: v for k, v in parts.items() if v is not None}
    lead = max(have, key=have.get)
    names = {"act": "planning activity", "pipe": "its housing pipeline", "ma": "office-to-residential (Class MA) conversions",
             "com": "new commercial floorspace", "transport": "growth in station use", "population": "population growth",
             "prices": "house-price momentum"}
    bits.append(f"{full} scores highest on {names[lead]} (top {max(1, 100 - parts[lead])}% of London).")
    bits.append(f"In the last 12 months: {fnum(sig['act'])} significant applications, {fnum(sig['pipe'])} net new home{'' if sig['pipe']==1 else 's'} proposed"
                + (f", {homes(sig['ma'] - 0.5 * sig['ma_n'])} via Class MA" if sig['ma_n'] else "")
                + (f" and {fnum(sig['com'])} m² of net commercial floorspace." if sig['com'] >= 500 else "."))
    o = off or {}
    facts = []
    if o.get("transport") is not None:
        facts.append(f"station use {pc(o['transport'])} ({o['transport_span']})")
    if o.get("population") is not None:
        facts.append(f"population {pc(o['population'])} ({o['population_span']})")
    if o.get("prices") is not None:
        facts.append(f"median sale price {pc(o['prices'])} on a year earlier, at £{o['median_price']:,.0f}")
    if facts:
        bits.append("Official statistics: " + "; ".join(facts) + ".")
    big = [s for s in schemes if (s.get("units") or 0) >= 10][:2]
    if big:
        bits.append("Largest live schemes: " + "; ".join(f"{s['site']} ({homes(s['units'])}, {s['status'].lower()}, ref {s['ref']})" for s in big) + ".")
    return " ".join(bits)


def build(today=None):
    today = today or dt.date.today()
    prior = today - dt.timedelta(days=30)
    dist_now, dist_prev = tiles(today), tiles(prior)
    import signals as official
    loaded, errors = official.load_all(today)
    odist, meta = {}, {}
    for name, (pts, m, kind) in loaded.items():
        agg = official.aggregate(pts, kind)
        minimum = {"transport": 1, "population": 3, "prices": 1}[kind]
        odist[name] = [a["growth"] for a in agg.values() if a["growth"] is not None and a["n"] >= minimum]
        if kind == "prices":
            odist["price_level"] = [a["median"] for a in agg.values() if a["median"] is not None]
        meta[name] = {**m, "tiles": len(odist[name])}
    span = {"transport": (meta.get("transport") or {}).get("tfl") or (meta.get("transport") or {}).get("orr") or "",
            "population": (meta.get("population") or {}).get("years", "")}
    out = []
    for n, full, boro, lat, lon in AREAS:
        r = area_query(lat, lon, today, top=12)
        sig = signals(r["aggregations"]); sig["ma_n"] = r["aggregations"]["ma"]["doc_count"]
        extra, offv, headroom = {}, {}, None
        for name, (pts, m, kind) in loaded.items():
            a = official.summarise(official.within(pts, lat, lon, RADIUS_KM), kind)
            g = a["growth"]
            extra[name] = pct(g, odist[name]) if g is not None and odist[name] else None
            offv[name] = g
            if kind == "prices" and a["median"] is not None:
                offv["median_price"] = a["median"]; offv["sales"] = a["sales"]
                headroom = 100 - pct(a["median"], odist["price_level"])
            if kind == "transport":
                offv["stations"] = a["n"]
        for k in OFFICIAL_W:
            extra.setdefault(k, None)
        offv["transport_span"], offv["population_span"] = span["transport"], span["population"]
        s, parts = score(sig, dist_now, extra)
        s_prev, _ = score(signals(area_query(lat, lon, prior)["aggregations"]), dist_prev, extra)
        schemes = []
        for h in r["hits"]["hits"]:
            src = h["_source"]; c = src.get("centroid") or {}
            if c and nearest(c["lat"], c["lon"]) != n:
                continue  # neighbourhood circles overlap: list a scheme only under its closest centre
            if re.search(r"invalid|refus|withdrawn|lapsed", src.get("status") or "", re.I):
                continue
            rd = (src.get("application_details") or {}).get("residential_details") or {}
            u = (rd.get("total_no_proposed_residential_units") or 0) - (rd.get("total_no_existing_residential_units") or 0)
            site = label(src.get("site_name"), src.get("street_name"))
            schemes.append({"ref": src.get("lpa_app_no"), "lpa": src.get("lpa_name"), "site": site, "units": u,
                            "status": src.get("status") or "", "valid": src.get("valid_date")})
        out.append({"n": n, "f": full, "b": boro, "lat": lat, "lon": lon, "s": s, "c": s - s_prev,
                    "u": fnum(sig["pipe"]), "x": [parts[k] for k in WEIGHTS], "hd": headroom,
                    "raw": {k: round(v) for k, v in sig.items()},
                    "off": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in offv.items()},
                    "schemes": schemes, "t": takeaway(full, sig, parts, schemes, offv)})
    out.sort(key=lambda d: -d["s"])
    return {"generated": today.isoformat(), "window_days": 365, "radius_km": RADIUS_KM, "tiles": len(dist_now),
            "weights": WEIGHTS, "labels": [LABELS[k] for k in WEIGHTS], "keys": list(WEIGHTS),
            "sources": SOURCES, "official": meta, "errors": errors,
            "source": "GLA Planning London Datahub, TfL, ORR, ONS, HM Land Registry", "areas": out}


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    data = build()
    # Refuse to publish if the Datahub returned obviously partial data (keeps last good file instead).
    live = sum(1 for a in data["areas"] if a["raw"]["act"] > 0)
    if data["tiles"] < 120 or live < len(AREAS) - 3:
        sys.exit(f"Datahub looks incomplete ({data['tiles']} tiles, {live}/{len(AREAS)} areas with filings); not writing.")
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "momentum.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"{data['generated']}: {len(data['areas'])} areas vs {data['tiles']} London tiles")
    for a in data["areas"]:
        print(f"  {a['s']:3d} ({a['c']:+d})  {a['n']:<15} x={a['x']}  raw={a['raw']}")
    if "--html" in sys.argv:
        f = pathlib.Path(sys.argv[sys.argv.index("--html") + 1])
        html = f.read_text()
        snap = "var MI=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";"
        new, k = re.subn(r"/\*MI\*/.*?/\*/MI\*/", lambda m: "/*MI*/" + snap + "/*/MI*/", html, flags=re.S)
        if k != 1:
            sys.exit("snapshot markers /*MI*/ ... /*/MI*/ not found in " + str(f))
        f.write_text(new)
        print("snapshot written to", f)


if __name__ == "__main__":
    # Public output must hold only the free top 6; publish.py handles that (and Supabase).
    import publish
    publish.main()
