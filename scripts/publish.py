#!/usr/bin/env python3
"""Weekly publish: Momentum Index + Monday Briefs.

  python3 scripts/publish.py [--html PATH] [--send]

- Builds the full index (scripts/momentum.py).
- Writes data/momentum.json with the TOP 6 only (public, free tier).
- If SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set:
    * stores the full snapshot (all neighbourhoods) in `snapshots` (paid users, history)
    * writes one brief per neighbourhood for this week into `briefs`
    * with --send, calls the send-briefs function (needs CRON_SECRET) to email paying users
Standard library only.
"""
import json, os, sys, pathlib, datetime as dt, urllib.request, html as H, re

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import momentum as M  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SB, KEY = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
FREE_TOP = 10


def sb(method, path, body=None, headers=None):
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(f"{SB}{path}", json.dumps(body).encode() if body is not None else None, h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode()
        return json.loads(t) if t else None


def public(data):
    d = {k: v for k, v in data.items() if k != "tile_scores"}
    d["areas"] = data["areas"][:FREE_TOP]
    d["tracked"] = len(data["areas"])
    return d

# What counts as a filing worth telling a developer about: new homes, office-to-home (Class MA),
# or at least 200 m2 of commercial space. Paperwork on old permissions, signs, windows and the like are left out.
BRIEF_WANT = {"bool": {"should": [{"range": {M.PROP: {"gte": 1}}}, {"range": {M.GAIN: {"gte": 200}}},
                                  {"term": {"application_type_full.raw": M.CLASS_MA}}, {"match_phrase": {"description": "class ma"}}],
                       "minimum_should_match": 1}}
NOISE = re.compile(r"pursuant to|details of condition|discharge|\bs106\b|section 106|section 73|variation of condition|deed of"
                   r"|certificate of lawful|lawful development|advertisement|illuminated|signage|fascia|shopfront|window"
                   r"|cladding|external wall|solar panel|\btrees?\b|telecom|street hub|pre-application", re.I)
BRIEF_SRC = ["lpa_app_no", "lpa_name", "site_name", "street_name", "description", "status", "decision", "valid_date",
             "decision_date", "application_type_full", "centroid", M.PROP, M.EXIST, M.GAIN, M.LOST]
CTX = {"tiles": {}, "ma": {}}   # local Momentum tiles + borough Class MA stats, filled in main() for the "why it matters" lines


def council_link(ref, lpa):
    """A web search for the reference, which usually finds the council's own page first (same as planning.html)."""
    import urllib.parse
    return "https://www.google.com/search?q=" + urllib.parse.quote(f'"{ref}" {lpa or ""} council planning application')


def why_line(s):
    """Why it matters, built only from the filing's own figures, its local Momentum tile and borough decision data."""
    import explore as X
    c = X.coord(s.get("centroid"))
    if not c:
        return ""
    r = X.row(s, c)
    z, x, y = X.M_tile(c[0], c[1])
    w, _ = X.why(r, CTX["tiles"].get(f"{z}/{x}/{y}"), CTX["ma"].get(r[8]), 150)
    return w


def brief_item(s, since, today):
    """A filing as a brief line, or None if it isn't worth a developer's attention."""
    import explore as X
    u, com = X.units_of(s)
    ma = bool(X.is_ma(s))
    v = X.dmy(s.get("valid_date"))
    if not v or v < since - dt.timedelta(days=1) or v > today + dt.timedelta(days=7):   # bad or far-off dates
        return None
    if not (u >= 1 or com >= 200 or ma) or (NOISE.search(s.get("description") or "") and u < 1 and not ma):
        return None
    kind = ("Office-to-home (Class MA)" if ma else "Major scheme" if (u >= 10 or com >= 1000)
            else "New homes" if u > 0 else "Commercial space")
    return {"ref": s.get("lpa_app_no"), "lpa": s.get("lpa_name"), "site": M.label(s.get("site_name"), s.get("street_name")),
            "units": max(u, 0), "com": max(com, 0), "status": X.short_status(s) or s.get("status") or "",
            "valid": s.get("valid_date"), "kind": kind, "desc": M.clip(s.get("description"), 220),
            "why": why_line(s), "url": council_link(s.get("lpa_app_no"), s.get("lpa_name"))}


def hits(body):
    """Run a brief query; if the stricter filter is ever rejected, fall back to the broad one (brief_item still filters)."""
    try:
        return M.q(body)["hits"]["hits"]
    except Exception as e:  # noqa: BLE001
        print(f"brief query fell back to the broad filter: {type(e).__name__}: {e}")
        f = [x for x in body["query"]["bool"]["filter"] if x is not BRIEF_WANT]
        body = {**body, "size": 150, "query": {"bool": {**body["query"]["bool"], "filter": f}}}
        return M.q(body)["hits"]["hits"]


def new_filings(area, since, seen):
    n, full, boro, lat, lon = area
    geo = {"geo_distance": {"distance": f"{M.RADIUS_KM}km", "centroid": {"lat": lat, "lon": lon}}}
    rng = {"range": {"valid_date": {"gte": since.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    import explore as X
    body = {"size": 80, "query": {"bool": {"filter": [rng, geo, M.QUALIFYING, BRIEF_WANT],
                                           "must_not": [M.terms("status", M.DEAD)] + X.NOT_DUP}},
            "sort": [{M.PROP: {"order": "desc", "missing": "_last"}}], "_source": BRIEF_SRC}
    out, today = [], dt.date.today()
    for h in hits(body):
        s = h["_source"]; c = s.get("centroid") or {}
        if s.get("lpa_app_no") in seen or (c and M.nearest(c["lat"], c["lon"]) != n):
            continue
        it = brief_item(s, since, today)
        if it:
            out.append(it)
    out.sort(key=lambda x: (-(x["units"] or 0), -(x["com"] or 0)))
    return out[:6]


def near_filings(lat, lon, radius_m, since, seen):
    geo = {"geo_distance": {"distance": f"{radius_m}m", "centroid": {"lat": lat, "lon": lon}}}
    rng = {"range": {"valid_date": {"gte": since.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    import explore as X
    body = {"size": 60, "query": {"bool": {"filter": [rng, geo, M.QUALIFYING, BRIEF_WANT],
                                           "must_not": [M.terms("status", M.DEAD)] + X.NOT_DUP}},
            "sort": [{M.PROP: {"order": "desc", "missing": "_last"}}], "_source": BRIEF_SRC}
    out, today = [], dt.date.today()
    import math
    for h in hits(body):
        s = h["_source"]
        if s.get("lpa_app_no") in seen:
            continue
        it = brief_item(s, since, today)
        if not it:
            continue
        c = s.get("centroid") or {}
        try:
            d = int(math.hypot((float(c["lon"]) - lon) * 69.4, (float(c["lat"]) - lat) * 111.2) * 1000)
        except (KeyError, TypeError, ValueError):
            d = 0
        out.append({"ref": it["ref"], "lpa": it["lpa"], "site": it["site"], "units": it["units"], "com": it["com"],
                    "kind": it["kind"], "status": it["status"], "dist": d, "why": it.get("why", ""), "url": it.get("url", ""),
                    "desc": it.get("desc", "")})
    out.sort(key=lambda x: (-(x["units"] or 0), -(x["com"] or 0), x["dist"]))
    return out[:8]


def decided_near(lat, lon, radius_m, since, seen, area_name=None):
    """Significant schemes within radius_m that were approved or refused since `since` (by the council's decision date)."""
    import explore as X
    geo = {"geo_distance": {"distance": f"{radius_m}m", "centroid": {"lat": lat, "lon": lon}}}
    by_dec = {"range": {"decision_date": {"gte": since.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    filed = {"range": {"valid_date": {"gte": (since - dt.timedelta(days=900)).strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    base = {"size": 80, "query": {"bool": {"filter": [geo, M.QUALIFYING, BRIEF_WANT], "must_not": X.NOT_DUP}},
            "sort": [{M.PROP: {"order": "desc", "missing": "_last"}}], "_source": BRIEF_SRC}
    try:
        b = json.loads(json.dumps(base)); b["query"]["bool"]["filter"].append(by_dec)
        rows = M.q(b)["hits"]["hits"]
    except Exception as e:  # noqa: BLE001  decision_date not searchable: scan recent decided filings instead
        print(f"decisions fell back to a scan: {type(e).__name__}: {e}")
        b = json.loads(json.dumps(base)); b["size"] = 400; b["query"]["bool"]["filter"].append(filed)
        try:
            rows = M.q(b)["hits"]["hits"]
        except Exception as e2:  # noqa: BLE001
            print(f"decisions skipped: {e2}"); return []
    out, today = [], dt.date.today()
    for h in rows:
        s = h["_source"]; c = X.coord(s.get("centroid"))
        st = X.short_status(s); d = X.dmy(s.get("decision_date"))
        if st not in ("Approved", "Refused") or not d or d < since or d > today or s.get("lpa_app_no") in seen:
            continue
        if area_name and c and M.nearest(c[0], c[1]) != area_name:
            continue
        it = brief_item({**s, "valid_date": d.strftime("%d/%m/%Y")}, since, today)   # same "worth it" test as filings
        if it:
            it["status"] = st; it["decided"] = d.isoformat(); it["valid"] = s.get("valid_date")
            if c:
                it["dist"] = int(M.km(lat, lon, c[0], c[1]) * 1000)
            out.append(it)
    out.sort(key=lambda x: (x["status"] != "Approved", -(x["units"] or 0), -(x["com"] or 0)))
    return out[:5]


def decisions(area, since, seen):
    n, full, boro, lat, lon = area
    return decided_near(lat, lon, int(M.RADIUS_KM * 1000), since, seen, n)


def london_top(since, seen):
    """The three biggest new filings anywhere in London, so every brief has something even in a quiet week."""
    import explore as X
    rng = {"range": {"valid_date": {"gte": since.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    geo = {"geo_bounding_box": {"centroid": M.BBOX}}
    body = {"size": 60, "query": {"bool": {"filter": [rng, geo, M.QUALIFYING, BRIEF_WANT],
                                           "must_not": [M.terms("status", M.DEAD)] + X.NOT_DUP}},
            "sort": [{M.PROP: {"order": "desc", "missing": "_last"}}], "_source": BRIEF_SRC}
    out, today = [], dt.date.today()
    try:
        rows = hits(body)
    except Exception as e:  # noqa: BLE001
        print(f"London top skipped: {e}"); return []
    for h in rows:
        s = h["_source"]
        if s.get("lpa_app_no") in seen:
            continue
        it = brief_item(s, since, today)
        if it and (it["units"] >= 10 or it["com"] >= 1000 or it["kind"].startswith("Office")):
            out.append(it)
    out.sort(key=lambda x: (-(x["units"] or 0), -(x["com"] or 0)))
    return out[:3]


def size_txt(i):
    return " · ".join(x for x in [f"{i['units']:,} home{'s' if i['units'] != 1 else ''}" if (i["units"] or 0) > 0 else "",
                                  f"{i['com']:,} m² commercial" if (i.get("com") or 0) >= 200 else ""] if x)


def li(i, decided=False):
    G = "color:#8c9ab3"
    tag = ""
    if decided:
        col = "#1fa971" if i["status"] == "Approved" else "#e05252"
        tag = f"<b style='color:{col}'>{H.escape(i['status'])}</b> · "
    meta = " · ".join(x for x in [size_txt(i), i["kind"], "" if decided else i["status"]] if x)
    why = f"<br><span>{H.escape(i['why'])}</span>" if i.get("why") and not decided else ""
    return (f"<li style='margin:0 0 10px'>{tag}<b>{H.escape(i['site'])}</b>: {H.escape(meta)}{why}<br>"
            f"<span style='{G}'>{H.escape(i['desc'])}</span><br>"
            f"<a href='{H.escape(i['url'])}' style='color:#4c9bff'>{H.escape(i['lpa'] or 'Council')} ref {H.escape(i['ref'] or '')} →</a></li>")


def brief_for(a, prev, items, decided=(), keys=None):
    d = (a["s"] - prev["s"]) if prev else a["c"]
    when = "since last week" if prev else "over 30 days"
    move = f"up {d} pts" if d > 0 else f"down {-d} pts" if d < 0 else "unchanged"
    bits = [f"{len(items)} new" if items else "", f"{len(decided)} decided" if decided else ""]
    title = f"{a['f']}: {a['s']}/100, {move} {when}" + (" · " + ", ".join(b for b in bits if b) if any(bits) else "")
    names = {"act": "planning activity", "pipe": "housing pipeline", "ma": "office-to-home conversions", "com": "commercial floorspace",
             "transport": "station use", "population": "population", "prices": "house prices"}
    tr = dict(zip(keys or [], a.get("tr") or []))
    up = [names[k] for k, v in tr.items() if v == "u" and k in names]
    dn = [names[k] for k, v in tr.items() if v == "d" and k in names]
    trend = " ".join(x for x in [f"Rising over 12 months: {', '.join(up)}." if up else "",
                                 f"Falling: {', '.join(dn)}." if dn else ""] if x)
    p = [f"<p>Momentum Index <b>{a['s']}/100</b> ({move} {when}). {H.escape(trend)}</p>"]
    if decided:
        p.append(f"<p><b>Decided this week</b></p><ul style='padding-left:18px'>" + "".join(li(i, True) for i in decided) + "</ul>")
    if items:
        units = sum(max(0, i["units"] or 0) for i in items)
        com = sum(max(0, i.get("com") or 0) for i in items)
        prop = " and ".join(x for x in [f"{units:,} net new home{'s' if units != 1 else ''}" if units else "",
                                         f"{com:,} m² of commercial space" if com else ""] if x)
        p.append(f"<p><b>{len(items)} new significant filing{'s' if len(items) != 1 else ''}</b>"
                 + (f", proposing {prop}" if prop else "") + "</p><ul style='padding-left:18px'>"
                 + "".join(li(i) for i in items) + "</ul>")
    if not items and not decided:
        p.append("<p>A quiet week here: no new homes, office-to-home conversions or sizeable commercial schemes were filed or decided.</p>")
    return title, "".join(p)


def main():
    week = dt.date.today()
    full = M.build(week)
    live = sum(1 for a in full["areas"] if a["raw"]["act"] > 0)
    if full["tiles"] < 120 or live < len(M.AREAS) - 3:
        sys.exit(f"Datahub looks incomplete ({full['tiles']} tiles, {live} areas); not publishing.")
    pub = public(full)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "momentum.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1))
    print(f"public index written: {len(pub['areas'])} of {pub['tracked']} areas")
    import explore
    print("postcode check + Class MA tracker:", explore.write_all(full, week))
    try:  # neighbourhood pages, Class MA page and sitemap, from the public data just written
        import pages
        print("SEO pages:", pages.write_all())
    except Exception as e:  # noqa: BLE001
        print(f"SEO pages skipped: {type(e).__name__}: {e}")
    # Other cities (no Supabase/briefs yet). A failure here never blocks London.
    import city, signals
    for c in city.CITY_AREAS:
        try:
            _, info = city.write(c, week)
            print(f"{c}:", info)
        except Exception as e:  # noqa: BLE001
            print(f"{c} skipped: {type(e).__name__}: {e}")
        finally:
            signals.configure("london")

    if "--html" in sys.argv:
        f = pathlib.Path(sys.argv[sys.argv.index("--html") + 1])
        snap = "var MI=" + json.dumps(pub, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";"
        txt, k = re.subn(r"/\*MI\*/.*?/\*/MI\*/", lambda m: "/*MI*/" + snap + "/*/MI*/", f.read_text(), flags=re.S)
        if k != 1:
            sys.exit("snapshot markers not found")
        f.write_text(txt); print("snapshot written to", f)

    if not (SB and KEY):
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: skipped snapshot, briefs and emails.")
        return
    up = {"Prefer": "resolution=merge-duplicates"}
    sb("POST", "/rest/v1/snapshots?on_conflict=generated", {"generated": full["generated"], "data": full}, up)
    prev_rows = sb("GET", f"/rest/v1/snapshots?select=generated,data&generated=lt.{full['generated']}&order=generated.desc&limit=1") or []
    prev = {a["n"]: a for a in prev_rows[0]["data"]["areas"]} if prev_rows else {}
    seen_rows = sb("GET", f"/rest/v1/briefs?select=data&week=gte.{(week - dt.timedelta(days=120)).isoformat()}&week=lt.{week.isoformat()}") or []
    seen = {r for row in seen_rows for r in (row["data"] or {}).get("refs", [])}
    dseen = {r for row in seen_rows for r in (row["data"] or {}).get("drefs", [])}
    lseen = {r for row in seen_rows for r in (row["data"] or {}).get("lrefs", [])}
    CTX["tiles"] = full.get("tile_scores", {})
    try:
        CTX["ma"] = {b["borough"]: b for b in json.loads((ROOT / "data" / "classma.json").read_text()).get("boroughs", [])}
    except (OSError, ValueError):
        pass
    since = week - dt.timedelta(days=21)
    top = london_top(since, lseen)
    rows = []
    for area in M.AREAS:
        a = next(x for x in full["areas"] if x["n"] == area[0])
        items = new_filings(area, since, seen)
        dec = decisions(area, since, dseen)
        pa = prev.get(a["n"])
        title, body = brief_for(a, pa, items, dec, full.get("keys"))
        rows.append({"week": week.isoformat(), "area": a["n"], "title": title, "body": body,
                     "data": {"score": a["s"], "move": (a["s"] - pa["s"]) if pa else a["c"], "name": a["f"],
                              "refs": [i["ref"] for i in items], "items": items,
                              "drefs": [i["ref"] for i in dec], "decided": dec,
                              "lrefs": [i["ref"] for i in top], "london": top}})
    sb("POST", "/rest/v1/briefs?on_conflict=week,area", rows, up)
    print(f"stored snapshot and {len(rows)} briefs for {week}")
    try:  # anonymous funnel counts are kept for two years (privacy policy)
        sb("DELETE", f"/rest/v1/events?created_at=lt.{(week - dt.timedelta(days=730)).isoformat()}", headers={"Prefer": "return=minimal"})
    except Exception as e:  # noqa: BLE001  (table not created yet)
        print(f"event clean-up skipped: {e}")

    # Alerts: new significant filings near each saved place (London places; Manchester has no open feed).
    places = sb("GET", "/rest/v1/saved_places?select=id,lat,lon,radius_m,postcode") or []
    prev = sb("GET", f"/rest/v1/alerts?select=place_id,items&week=lt.{week.isoformat()}&week=gte.{(week - dt.timedelta(days=120)).isoformat()}") or []
    seen_by = {}
    for r in prev:
        seen_by.setdefault(r["place_id"], set()).update(i.get("ref") for i in (r["items"] or []))
    out = []
    for pl in places:
        if not (51.28 < pl["lat"] < 51.70 and -0.52 < pl["lon"] < 0.34):
            continue
        items = near_filings(pl["lat"], pl["lon"], pl["radius_m"], week - dt.timedelta(days=14), seen_by.get(pl["id"], set()))
        out.append({"place_id": pl["id"], "week": week.isoformat(), "items": items})
    if out:
        sb("POST", "/rest/v1/alerts?on_conflict=place_id,week", out, up)
    print(f"alerts: {sum(1 for o in out if o['items'])} of {len(out)} saved places have new filings")

    if "--send" in sys.argv:
        req = urllib.request.Request(f"{SB}/functions/v1/send-briefs", json.dumps({"week": week.isoformat()}).encode(),
                                     {"Content-Type": "application/json", "x-cron-secret": os.environ["CRON_SECRET"]}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            print("emails:", r.read().decode())


if __name__ == "__main__":
    main()
