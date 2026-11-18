#!/usr/bin/env python3
"""Public data for the postcode check and the Class MA tracker (written by publish.py).

  data/tiles.json        Momentum score for every ~3 km map tile in London
  data/pts/<x>_<y>.json  significant planning applications (last 24 months) per zoom-13 tile
  data/classma.json      Class MA (office/shop-to-home) league table by borough + latest filings
  data/feed.json         latest significant filings with plain-English summaries (planning feed, sample brief)
"""
import json, re, statistics, datetime as dt, pathlib, shutil
import momentum as M

ROOT = pathlib.Path(__file__).resolve().parent.parent
LONDON_BOX = {"geo_bounding_box": {"centroid": M.BBOX}}
NOT_DUP = [M.terms("application_type_full", M.DUPLICATE_TYPES + ["Lawful development: Proposed use", "Lawful development: Existing use"]),
           {"term": {"application_type.raw": "Householder"}}]
APPROVED = {"approved", "parg", "not required", "approve", "allowed", "granted", "prior approval not required"}
REFUSED = {"refused", "dismissed", "refuse"}


def dmy(s):
    try:
        return dt.datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def month_windows(start, end):
    d = start
    while d < end:
        nxt = min(end, (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1))
        yield d, nxt - dt.timedelta(days=1)
        d = nxt


def rng(a, b):
    return {"range": {"valid_date": {"gte": a.strftime("%d/%m/%Y"), "lte": b.strftime("%d/%m/%Y"), "format": "dd/MM/yyyy"}}}


SRC = ["lpa_app_no", "lpa_name", "site_name", "street_name", "description", "status", "decision", "valid_date", "decision_date",
       "application_type_full", "centroid", M.PROP, M.EXIST, M.GAIN, M.LOST]


def units_of(s):
    ad = s.get("application_details") or {}
    rd = ad.get("residential_details") or {}; nr = ad.get("non_residential_details") or {}
    u = (rd.get("total_no_proposed_residential_units") or 0) - (rd.get("total_no_existing_residential_units") or 0)
    c = (nr.get("total_gia_gained") or 0) - (nr.get("total_gia_lost") or 0)
    return int(u), int(c)


def is_ma(s):
    return M.CLASS_MA == (s.get("application_type_full") or "") or (
        not s.get("application_type_full") and re.search(r"class ma\b", s.get("description") or "", re.I))


def short_status(s):
    st = (s.get("decision") or s.get("status") or "").strip()
    low = st.lower()
    if low in APPROVED or low.startswith("approv") or "granted" in low:
        return "Approved"
    if low in REFUSED or low.startswith("refus"):
        return "Refused"
    if "withdraw" in low:
        return "Withdrawn"
    if "appeal" in low:
        return "At appeal"
    if "commenc" in low:
        return "Started"
    if "complet" in low:
        return "Completed"
    return "Pending"


def significant(today):
    """Applications in the last 24 months proposing homes, commercial space or Class MA conversions."""
    want = {"bool": {"should": [{"range": {M.PROP: {"gte": 1}}}, {"range": {M.GAIN: {"gte": 100}}},
                                {"term": {"application_type_full.raw": M.CLASS_MA}}], "minimum_should_match": 1}}
    out = []
    for a, b in month_windows(today - dt.timedelta(days=730), today + dt.timedelta(days=1)):
        body = {"size": 9000, "_source": SRC, "query": {"bool": {"filter": [rng(a, b), LONDON_BOX, want], "must_not": NOT_DUP}}}
        out.extend(h["_source"] for h in M.q(body)["hits"]["hits"])
    return out


def class_ma(today):
    out = []
    ma = {"bool": {"should": [{"term": {"application_type_full.raw": M.CLASS_MA}},
                              {"bool": {"must": [{"match_phrase": {"description": "class ma"}}],
                                        "must_not": [{"exists": {"field": "application_type_full"}}]}}], "minimum_should_match": 1}}
    for a, b in ((today - dt.timedelta(days=730), today - dt.timedelta(days=365)), (today - dt.timedelta(days=365), today + dt.timedelta(days=1))):
        body = {"size": 9000, "_source": SRC, "query": {"bool": {"filter": [rng(a, b), ma]}}}
        out.extend(h["_source"] for h in M.q(body)["hits"]["hits"])
    return out


def coord(c):
    """Datahub centroids come as {lat, lon} numbers, numeric strings, or a "lat,lon" string."""
    try:
        if isinstance(c, str):
            a, b = c.split(","); return float(a), float(b)
        if isinstance(c, dict):
            return float(c["lat"]), float(c["lon"])
    except (KeyError, TypeError, ValueError):
        pass
    return None


def row(s, c):
    u, com = units_of(s)
    kind = "ma" if is_ma(s) else ("major" if u >= 10 or com >= 1000 else ("res" if u > 0 else "com"))
    v = dmy(s.get("valid_date"))
    return [round(c[0], 5), round(c[1], 5), u, max(com, 0), kind, short_status(s), v.isoformat() if v else "",
            s.get("lpa_app_no") or "", s.get("lpa_name") or "", M.label(s.get("site_name"), s.get("street_name"))[:70],
            M.tidy(s.get("description"))[:160]]


def build_points(today, outdir):
    rows = significant(today)
    by = {}
    for s in rows:
        c = coord(s.get("centroid"))
        if not c or not (51.28 < c[0] < 51.70 and -0.52 < c[1] < 0.34):
            continue
        r = row(s, c)
        if r[4] != "ma" and r[2] < 2 and r[3] < 100:
            continue  # skip single-home tweaks; keep schemes, conversions and commercial space
        z, x, y = M_tile(r[0], r[1])
        by.setdefault(f"{x}_{y}", []).append(r)
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    for k, v in by.items():
        v.sort(key=lambda r: (-(r[2] or 0), -(r[3] or 0)))
        (outdir / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    return sum(len(v) for v in by.values()), len(by)


def M_tile(lat, lon, z=13):
    import math
    n = 2 ** z
    return z, int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def build_classma(today):
    rows = class_ma(today)
    yr = today - dt.timedelta(days=365)
    bor = {}
    for s in rows:
        b = s.get("lpa_name") or "Unknown"
        d = bor.setdefault(b, {"filed_12m": 0, "homes_12m": 0, "approved": 0, "refused": 0, "pending": 0, "days": []})
        v, dd = dmy(s.get("valid_date")), dmy(s.get("decision_date"))
        u, _ = units_of(s)
        st = short_status(s)
        if v and v >= yr:
            d["filed_12m"] += 1; d["homes_12m"] += max(u, 0)
        if st in ("Approved", "Started", "Completed"):
            d["approved"] += 1
        elif st in ("Refused",):
            d["refused"] += 1
        elif st == "Pending":
            d["pending"] += 1
        if v and dd and st in ("Approved", "Refused", "Started", "Completed") and dd >= v and dd.year < 2100 and (dd - v).days < 400:
            d["days"].append((dd - v).days)
    table = []
    for b, d in bor.items():
        dec = d["approved"] + d["refused"]
        table.append({"borough": b, "filed_12m": d["filed_12m"], "homes_12m": d["homes_12m"], "decided_24m": dec,
                      "approval_rate": round(d["approved"] / dec, 3) if dec >= 5 else None,
                      "median_days": int(statistics.median(d["days"])) if len(d["days"]) >= 5 else None,
                      "pending": d["pending"]})
    table.sort(key=lambda r: (-r["filed_12m"], -r["homes_12m"]))
    tot_dec = sum(r["decided_24m"] for r in table); tot_app = sum(bor[r["borough"]]["approved"] for r in table)
    latest = sorted((s for s in rows if dmy(s.get("valid_date")) and units_of(s)[0] >= 2 and short_status(s) != "Withdrawn"), key=lambda s: dmy(s["valid_date"]), reverse=True)[:12]
    alld = [x for d in bor.values() for x in d["days"]]
    return {"generated": today.isoformat(), "boroughs": table,
            "london": {"filed_12m": sum(r["filed_12m"] for r in table), "homes_12m": sum(r["homes_12m"] for r in table),
                       "approval_rate": round(tot_app / tot_dec, 3) if tot_dec else None,
                       "median_days": int(statistics.median(alld)) if alld else None},
            "latest": [{"borough": s.get("lpa_name"), "site": M.label(s.get("site_name"), s.get("street_name"))[:70],
                        "homes": max(units_of(s)[0], 0), "status": short_status(s), "valid": dmy(s["valid_date"]).isoformat(),
                        "ref": s.get("lpa_app_no")} for s in latest]}



def summary(r):
    """One plain-English line built only from the filing's own figures (no guesswork)."""
    u, com, kind, status = max(0, r[2] or 0), r[3] or 0, r[4], r[5]
    done = status in ("Approved", "Started", "Completed")
    if kind == "ma" and not u:
        return ("Approved: offices or shops to become homes (number not stated)." if done
                else "Offices or shops proposed for conversion to homes (number not stated).")
    if kind == "ma":
        return (f"Approved: offices or shops to become {u:,} home{'s' if u != 1 else ''}." if done
                else f"Offices or shops proposed for conversion to {u:,} home{'s' if u != 1 else ''}.")
    parts = []
    if u: parts.append(f"{u:,} new home{'s' if u != 1 else ''}")
    if com >= 100: parts.append(f"{com:,} m² of commercial space")
    what = " and ".join(parts) or "a major scheme"
    return f"Approved: {what}." if done else f"{what[0].upper() + what[1:]} proposed."


def build_feed(today, datadir, days=60, limit=30):
    """Latest significant filings across London, for the planning feed and the sample brief."""
    rows = []
    for f in (datadir / "pts").glob("*.json"):
        rows += json.loads(f.read_text())
    since = (today - dt.timedelta(days=days)).isoformat()
    keep = [r for r in rows if (r[4] == "major" or (r[4] == "ma" and (r[2] or 0) >= 5))
            and r[6] and r[6] >= since and r[5] not in ("Refused", "Withdrawn")]  # schemes that matter: majors and conversions of 5+ homes
    keep.sort(key=lambda r: (r[6], r[2] or 0), reverse=True)
    out = [{"borough": r[8], "site": r[9], "ref": r[7], "kind": r[4], "homes": max(0, r[2] or 0), "commercial_m2": r[3],
            "status": r[5], "valid": r[6], "summary": summary(r), "description": r[10]} for r in keep[:limit]]
    feed = {"generated": today.isoformat(), "window_days": days, "source": "GLA Planning London Datahub", "rows": out}
    (datadir / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    return len(out)

def write_all(full, today=None):
    today = today or dt.date.today()
    data = ROOT / "data"
    ts = {"generated": full["generated"], "radius_km": full["radius_km"], "labels": full["labels"], "keys": full["keys"],
          "weights": full["weights"], "bench": full.get("bench"), "tiles": full.get("tile_scores", {}),
          "areas": [{"n": a["n"], "f": a["f"], "lat": a["lat"], "lon": a["lon"]} for a in full["areas"]]}
    (data / "tiles.json").write_text(json.dumps(ts, ensure_ascii=False, separators=(",", ":")))
    n, files = build_points(today, data / "pts")
    cm = build_classma(today)
    (data / "classma.json").write_text(json.dumps(cm, ensure_ascii=False, indent=1))
    fd = build_feed(today, data)
    return {"tiles": len(ts["tiles"]), "applications": n, "files": files, "classma_boroughs": len(cm["boroughs"]), "feed": fd}
