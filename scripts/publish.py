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
FREE_TOP = 6


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


def new_filings(area, since, seen):
    n, full, boro, lat, lon = area
    geo = {"geo_distance": {"distance": f"{M.RADIUS_KM}km", "centroid": {"lat": lat, "lon": lon}}}
    rng = {"range": {"valid_date": {"gte": since.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}
    body = {"size": 40, "query": {"bool": {"filter": [rng, geo, M.QUALIFYING], "must_not": [M.terms("status", M.DEAD)]}},
            "sort": [{M.PROP: {"order": "desc", "missing": "_last"}}],
            "_source": ["lpa_app_no", "lpa_name", "site_name", "street_name", "description", "status", "valid_date",
                        "application_type_full", "centroid", M.PROP, M.EXIST]}
    out = []
    for h in M.q(body)["hits"]["hits"]:
        s = h["_source"]; c = s.get("centroid") or {}
        if s.get("lpa_app_no") in seen or (c and M.nearest(c["lat"], c["lon"]) != n):
            continue
        rd = (s.get("application_details") or {}).get("residential_details") or {}
        units = (rd.get("total_no_proposed_residential_units") or 0) - (rd.get("total_no_existing_residential_units") or 0)
        kind = "Class MA conversion" if "Use Class E) to Dwellinghouses" in (s.get("application_type_full") or "") or re.search(r"class ma", s.get("description") or "", re.I) else (s.get("application_type_full") or "Application")
        out.append({"ref": s["lpa_app_no"], "lpa": s.get("lpa_name"), "site": M.label(s.get("site_name"), s.get("street_name")),
                    "units": units, "status": s.get("status") or "", "valid": s.get("valid_date"), "kind": kind,
                    "desc": M.tidy(s.get("description"))[:220]})
    out.sort(key=lambda x: -(x["units"] or 0))
    return out[:6]


def brief_for(a, prev, items):
    d = (a["s"] - prev["s"]) if prev else a["c"]
    when = "since last week" if prev else "over 30 days"
    move = f"up {d} pts" if d > 0 else f"down {-d} pts" if d < 0 else "unchanged"
    title = f"{a['f']}: {a['s']}/100, {move} {when}"
    units = sum(max(0, i["units"] or 0) for i in items)
    p = [f"<p>Momentum Index <b>{a['s']}/100</b> ({move} {when}). {H.escape(a['t'])}</p>"]
    if items:
        p.append(f"<p><b>{len(items)} new significant filing{'s' if len(items) != 1 else ''}</b>"
                 + (f" proposing {units:,} net new homes" if units else "") + ":</p><ul>")
        for i in items:
            u = f"{i['units']} homes · " if (i["units"] or 0) > 0 else ""
            p.append(f"<li><b>{H.escape(i['site'])}</b>: {u}{H.escape(i['kind'])} · {H.escape(i['status'])} "
                     f"<span style='color:#8c9ab3'>(ref {H.escape(i['ref'])}, {H.escape(i['lpa'] or '')})</span><br>"
                     f"<span style='color:#8c9ab3'>{H.escape(i['desc'])}</span></li>")
        p.append("</ul>")
    else:
        p.append("<p>No new significant filings this week.</p>")
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

    if "--send" in sys.argv:
        req = urllib.request.Request(f"{SB}/functions/v1/send-briefs", json.dumps({"week": week.isoformat()}).encode(),
                                     {"Content-Type": "application/json", "x-cron-secret": os.environ["CRON_SECRET"]}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            print("emails:", r.read().decode())


if __name__ == "__main__":
    main()
