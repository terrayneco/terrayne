#!/usr/bin/env python3
"""Weekly publish: Momentum Index + Monday briefs.

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
             "application_type_full", "centroid", M.PROP, M.EXIST, M.GAIN, M.LOST]


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
            "valid": s.get("valid_date"), "kind": kind, "desc": M.clip(s.get("description"), 220)}


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
                    "kind": it["kind"], "status": it["status"], "dist": d})
    out.sort(key=lambda x: (-(x["units"] or 0), -(x["com"] or 0), x["dist"]))
    return out[:8]


def brief_for(a, prev, items):
    d = (a["s"] - prev["s"]) if prev else a["c"]
    when = "since last week" if prev else "over 30 days"
    move = f"up {d} pts" if d > 0 else f"down {-d} pts" if d < 0 else "unchanged"
    title = f"{a['f']}: {a['s']}/100, {move} {when}"
    units = sum(max(0, i["units"] or 0) for i in items)
    com = sum(max(0, i.get("com") or 0) for i in items)
    p = [f"<p>Momentum Index <b>{a['s']}/100</b> ({move} {when}). {H.escape(a['t'])}</p>"]
    if items:
        prop = " and ".join(x for x in [f"{units:,} net new home{'s' if units != 1 else ''}" if units else "",
                                         f"{com:,} m² of commercial space" if com else ""] if x)
        p.append(f"<p><b>{len(items)} new significant filing{'s' if len(items) != 1 else ''}</b>"
                 + (f" proposing {prop}" if prop else "") + ":</p><ul>")
        for i in items:
            u = (f"{i['units']} home{'s' if i['units'] != 1 else ''} · " if (i["units"] or 0) > 0 else "") + \
                (f"{i['com']:,} m² commercial · " if (i.get("com") or 0) >= 200 else "")
            p.append(f"<li><b>{H.escape(i['site'])}</b>: {u}{H.escape(i['kind'])} · {H.escape(i['status'])} "
                     f"<span style='color:#8c9ab3'>(ref {H.escape(i['ref'])}, {H.escape(i['lpa'] or '')})</span><br>"
                     f"<span style='color:#8c9ab3'>{H.escape(i['desc'])}</span></li>")
        p.append("</ul>")
    else:
        p.append("<p>No new homes, office-to-home conversions or sizeable commercial schemes were filed nearby this week.</p>")
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
    since = week - dt.timedelta(days=21)
    rows = []
    for area in M.AREAS:
        a = next(x for x in full["areas"] if x["n"] == area[0])
        items = new_filings(area, since, seen)
        title, body = brief_for(a, prev.get(a["n"]), items)
        rows.append({"week": week.isoformat(), "area": a["n"], "title": title, "body": body,
                     "data": {"score": a["s"], "refs": [i["ref"] for i in items], "items": items}})
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
