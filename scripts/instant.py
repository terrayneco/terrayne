#!/usr/bin/env python3
"""Same-day alerts for Team customers.

  python3 scripts/instant.py [--dry-run]

Runs Tuesday to Friday (GitHub Action .github/workflows/alerts.yml). For every saved place owned by a
Team (enterprise) account, it looks for big new filings (10+ homes, 1,000+ m2 of commercial space, or
office-to-home / Class MA) and big schemes approved or refused nearby. Anything not already sent for that
place goes to the send-briefs Edge Function, which emails the Team members who have same-day alerts on.
Sent items are recorded in `instant_alerts` so nothing is sent twice. Needs SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY and CRON_SECRET. Standard library only.
"""
import json, os, sys, pathlib, datetime as dt, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import publish as P  # noqa: E402

LOOKBACK = 10   # days: councils often add filings to the Datahub some days after they are valid


def big(i):
    return (i["units"] or 0) >= 10 or (i.get("com") or 0) >= 1000 or i["kind"].startswith("Office")


def main():
    if not (P.SB and P.KEY):
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    dry = "--dry-run" in sys.argv
    today = dt.date.today()
    since = today - dt.timedelta(days=LOOKBACK)
    places = P.sb("GET", "/rest/v1/saved_places?select=id,owner,label,postcode,lat,lon,radius_m") or []
    plans = {}
    out = []
    for pl in places:
        if not (51.28 < pl["lat"] < 51.70 and -0.52 < pl["lon"] < 0.34):
            continue
        o = pl["owner"]
        if o not in plans:
            plans[o] = P.sb("POST", "/rest/v1/rpc/effective_plan", {"uid": o})
        if plans[o] != "enterprise":
            continue
        done = P.sb("GET", f"/rest/v1/instant_alerts?select=ref,kind&place_id=eq.{pl['id']}") or []
        sent_new = {d["ref"] for d in done if d["kind"] == "new"}
        sent_dec = {d["ref"] for d in done if d["kind"] == "decided"}
        # Filings already listed in a Monday Brief alert for this place aren't news either.
        mon = P.sb("GET", f"/rest/v1/alerts?select=items&place_id=eq.{pl['id']}&week=gte.{(today - dt.timedelta(days=21)).isoformat()}") or []
        sent_new |= {i.get("ref") for r in mon for i in (r["items"] or [])}
        new = [dict(i, alert="new") for i in P.near_filings(pl["lat"], pl["lon"], pl["radius_m"], since, sent_new) if big(i)]
        dec = [dict(i, alert="decided") for i in P.decided_near(pl["lat"], pl["lon"], pl["radius_m"], since, sent_dec) if big(i)]
        items = (dec + new)[:8]
        if items:
            out.append({"place_id": pl["id"], "items": items})
    print(f"same-day alerts: {len(out)} Team places with something new")
    if dry or not out:
        print(json.dumps(out, indent=1, ensure_ascii=False)[:4000])
        return
    req = urllib.request.Request(f"{P.SB}/functions/v1/send-briefs", json.dumps({"instant": out}).encode(),
                                 {"Content-Type": "application/json", "x-cron-secret": os.environ["CRON_SECRET"]}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        print("emails:", r.read().decode())
    rows = [{"place_id": o["place_id"], "ref": i["ref"], "kind": i["alert"], "item": i} for o in out for i in o["items"]]
    P.sb("POST", "/rest/v1/instant_alerts?on_conflict=place_id,ref,kind", rows,
         {"Prefer": "resolution=ignore-duplicates,return=minimal"})


if __name__ == "__main__":
    main()
