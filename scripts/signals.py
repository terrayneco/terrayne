#!/usr/bin/env python3
"""Official non-planning signals for the Momentum Index. Standard library only.

Sources (all official, open licence):
  - Transport: TfL Annual Station Counts (Underground, DLR, Overground, Elizabeth line) and
    ORR Estimates of Station Usage (National Rail); station locations from DfT NaPTAN.
  - Population: ONS small-area (LSOA, 2021-based) mid-year population estimates via Nomis;
    LSOA centre points from ONS Open Geography (LSOA 2021 boundaries).
  - House prices: HM Land Registry Price Paid Data; postcode locations from OS Code-Point Open
    (British National Grid, converted to WGS84 here).

Every source yields points (lat, lon, values). Each signal is aggregated over a neighbourhood circle
and over every zoom-13 map tile in Greater London, so it can be scored as a percentile like the
planning signals. Downloads are cached in .cache/ (git-ignored) for a week.
"""
import csv, io, json, math, re, statistics, time, urllib.parse, urllib.request, zipfile, pathlib, datetime as dt
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
UA = {"User-Agent": "terrayne-momentum-index/1.0"}
# City settings. configure("manchester") switches every loader below to that city.
CITIES = {
    "london": {"box": (51.28, 51.70, -0.52, 0.34), "county": {"GREATER LONDON"}, "nomis": "2013265927TYPE151",
               "orr_region": "London", "tfl": True,
               "pc_areas": ["e", "ec", "n", "nw", "se", "sw", "w", "wc", "br", "cr", "da", "en", "ha", "ig", "kt", "rm", "sm", "tw", "ub", "wd"]},
    "manchester": {"box": (53.33, 53.70, -2.75, -1.90), "county": {"GREATER MANCHESTER"}, "nomis": "2013265922TYPE151",
                   "orr_region": "North West", "tfl": False, "pc_areas": ["m", "ol", "bl", "wn", "sk", "wa"]},
}
CITY = "london"
LONDON = CITIES["london"]["box"]  # lat min/max, lon min/max of the current city (name kept for compatibility)


def configure(city):
    global CITY, LONDON
    CITY, LONDON = city, CITIES[city]["box"]


def cfg(k):
    return CITIES[CITY][k]


def fetch(url, name, max_age_days=7, timeout=300):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / name
    if p.exists() and time.time() - p.stat().st_mtime < max_age_days * 86400:
        return p
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(p.with_suffix(p.suffix + ".part"), "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    p.with_suffix(p.suffix + ".part").replace(p)
    return p


def in_london(lat, lon):
    return LONDON[0] < lat < LONDON[1] and LONDON[2] < lon < LONDON[3]


def tile(lat, lon, z=13):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return f"{z}/{x}/{y}"


def km(a, b, c, d):
    return math.hypot((d - b) * 111.32 * math.cos(math.radians((a + c) / 2)), (c - a) * 110.57)


# ---------- British National Grid -> WGS84 (OS formulae + Helmert) ----------
def bng_to_wgs84(E, N):
    a, b = 6377563.396, 6356256.909
    F0, lat0, lon0, N0, E0 = 0.9996012717, math.radians(49), math.radians(-2), -100000, 400000
    e2 = 1 - (b * b) / (a * a); n = (a - b) / (a + b)
    lat, M = lat0, 0
    while True:
        lat = (N - N0 - M) / (a * F0) + lat
        M = b * F0 * ((1 + n + 5 / 4 * n**2 + 5 / 4 * n**3) * (lat - lat0)
                      - (3 * n + 3 * n**2 + 21 / 8 * n**3) * math.sin(lat - lat0) * math.cos(lat + lat0)
                      + (15 / 8 * n**2 + 15 / 8 * n**3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0))
                      - (35 / 24 * n**3) * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0)))
        if abs(N - N0 - M) < 1e-5:
            break
    s, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * F0 / math.sqrt(1 - e2 * s * s); rho = a * F0 * (1 - e2) / (1 - e2 * s * s) ** 1.5; eta2 = nu / rho - 1
    VII = t / (2 * rho * nu); VIII = t / (24 * rho * nu**3) * (5 + 3 * t * t + eta2 - 9 * t * t * eta2)
    IX = t / (720 * rho * nu**5) * (61 + 90 * t * t + 45 * t**4)
    X = 1 / (c * nu); XI = 1 / (c * 6 * nu**3) * (nu / rho + 2 * t * t)
    XII = 1 / (c * 120 * nu**5) * (5 + 28 * t * t + 24 * t**4); XIIA = 1 / (c * 5040 * nu**7) * (61 + 662 * t * t + 1320 * t**4 + 720 * t**6)
    dE = E - E0
    phi = lat - VII * dE**2 + VIII * dE**4 - IX * dE**6
    lam = lon0 + X * dE - XI * dE**3 + XII * dE**5 - XIIA * dE**7
    # OSGB36 -> WGS84 Helmert
    H = 0
    x = (nu / F0 + H) * math.cos(phi) * math.cos(lam); y = (nu / F0 + H) * math.cos(phi) * math.sin(lam)
    z = ((1 - e2) * nu / F0 + H) * math.sin(phi)
    tx, ty, tz, s_ = 446.448, -125.157, 542.060, -20.4894e-6
    rx, ry, rz = [math.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421)]
    x2 = tx + (1 + s_) * x - rz * y + ry * z; y2 = ty + rz * x + (1 + s_) * y - rx * z; z2 = tz - ry * x + rx * y + (1 + s_) * z
    a2, b2 = 6378137.000, 6356752.3141; e22 = 1 - (b2 * b2) / (a2 * a2); p = math.hypot(x2, y2)
    la = math.atan2(z2, p * (1 - e22))
    for _ in range(10):
        nu2 = a2 / math.sqrt(1 - e22 * math.sin(la) ** 2); la = math.atan2(z2 + e22 * nu2 * math.sin(la), p)
    return math.degrees(la), math.degrees(math.atan2(y2, x2))


# ---------- spreadsheet readers (xlsx / ods) without third-party libraries ----------
def xlsx_rows(path):
    z = zipfile.ZipFile(path); ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    sheet = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
    for row in ET.fromstring(z.read(sheet)).iter("{%s}row" % ns["m"]):
        out = {}
        for c in row.findall("m:c", ns):
            col = re.match(r"[A-Z]+", c.get("r")).group(0); v = c.find("m:v", ns); t = c.get("t")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            elif v is None:
                continue
            else:
                val = ss[int(v.text)] if t == "s" else v.text
            out[col] = val
        yield out


def ods_rows(path, sheet_hint=None):
    z = zipfile.ZipFile(path)
    T = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"; X = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    root = ET.fromstring(z.read("content.xml"))
    tables = list(root.iter("{%s}table" % T))
    tbl = next((t for t in tables if sheet_hint and sheet_hint in (t.get("{%s}name" % T) or "")), tables[-1])
    for r in tbl.iter("{%s}table-row" % T):
        vals = []
        for c in r:
            rep = int(c.get("{%s}number-columns-repeated" % T, "1"))
            v = c.get("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value")
            if v is None:
                v = " ".join("".join(p.itertext()) for p in c.iter("{%s}p" % X))
            vals.extend([v] * min(rep, 50))
        yield vals


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------- transport ----------
ALIAS = {"bank and monument": "bank", "heathrow terminals 123": "heathrow terminals 2 and 3", "norwood jn": "norwood junction"}


def norm_station(s):
    s = re.sub(r"\((bak|dis|h&c|cir|nr|lu|dlr|el|lo)\)", " ", s, flags=re.I)
    s = re.sub(r"\s(NR|LU|DLR|EL)$", "", s.strip())
    s = s.lower().replace("&", " and ").replace("st.", "st ").replace("'", "").replace("’", "")
    s = re.sub(r"\((london|ldn|lu|dlr|lo|el|tfl|met|h and c|district|circle|bakerloo|central|northern|jubilee|piccadilly|victoria|elizabeth line|underground|rail|national rail)[^)]*\)", " ", s)
    s = re.sub(r"\b(underground|dlr|rail|railway|overground|elizabeth line|tram|stop|station|lu|lo|el|tfl|london)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIAS.get(s, s)


def station_points():
    """{normalised name: (lat, lon)} for rail/metro stations in London."""
    p = fetch("https://naptan.api.dft.gov.uk/v1/access-nodes?atcoAreaCodes=910,940&dataFormat=csv", "naptan_rail.csv", 30)
    pts = {}
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if r["StopType"] not in ("RLY", "MET") or r["Status"] != "active":
            continue
        lat, lon = num(r["Latitude"]), num(r["Longitude"])
        if lat and lon and in_london(lat, lon):
            pts.setdefault(norm_station(r["CommonName"]), (lat, lon))
    return pts


def tfl_counts(year):
    lst = urllib.request.urlopen(urllib.request.Request(
        f"https://s3-eu-west-1.amazonaws.com/crowding.data.tfl.gov.uk/?list-type=2&prefix=Annual%20Station%20Counts/{year}/", headers=UA), timeout=60).read().decode()
    key = next(k for k in re.findall(r"<Key>([^<]*)</Key>", lst) if "Annualised" in k and k.endswith(".xlsx"))
    f = fetch("https://crowding.data.tfl.gov.uk/" + urllib.parse.quote(key), f"tfl_ac{year}.xlsx", 60)
    rows = list(xlsx_rows(f)); hdr = None; out = {}
    for r in rows:
        if hdr is None and "Station" in r.values() and "Mode" in r.values():
            hdr = {v: k for k, v in r.items()}
            continue
        if hdr:
            name = r.get(hdr["Station"]); mode = r.get(hdr["Mode"])
            col = hdr.get("Annualised") or (max(r, key=lambda c: (len(c), c)) if r else None)
            v = num(r.get(col))
            if name and mode and v:
                out[(mode, name)] = v
    return out


def orr_counts():
    """National Rail station entries+exits for the latest two available years: {name: (latest, earlier)}."""
    f = fetch("https://dataportal.orr.gov.uk/media/1908/table-1415-time-series-of-passenger-entries-and-exits-and-interchanges-by-station.ods",
              "orr_1415.ods", 60)
    rows = list(ods_rows(f, "1415a"))
    hi = next(i for i, r in enumerate(rows) if any("Station name" in str(c) for c in r))
    hdr = rows[hi]
    cols = [i for i, h in enumerate(hdr) if re.match(r"Apr \d{4} to Mar \d{4}", str(h))]
    region = next((i for i, h in enumerate(hdr) if "Region" in str(h)), None)
    name_i = next(i for i, h in enumerate(hdr) if "Station name" in str(h))
    if len(cols) < 3:
        return {}, None
    latest, earlier = cols[-1], cols[-3]  # two years apart
    out = {}
    for r in rows[hi + 1:]:
        if len(r) <= latest or (region is not None and cfg("orr_region") not in str(r[region])):
            continue
        a, b = num(r[latest]), num(r[earlier])
        if a and b:
            out[r[name_i]] = (a, b)
    first = re.sub(r" \[.*", "", str(hdr[earlier]))
    return out, f"ORR {first} → {hdr[latest]}"


def transport_points():
    pts = station_points()
    yrs = []
    if not cfg("tfl"):
        yrs = None
    for y in (range(dt.date.today().year, dt.date.today().year - 4, -1) if yrs is not None else []):
        try:
            c = tfl_counts(y)
            if c:
                yrs.append((y, c))
        except (StopIteration, OSError):
            continue
        if len(yrs) == 3:
            break
    out, seen, unmatched = [], set(), 0
    label = None
    yrs = yrs or []
    if len(yrs) >= 2:
        (y1, now), (y0, prev) = yrs[0], yrs[-1]  # compare across two years where available
        label = f"TfL {y0}→{y1}"
        bykey, disp = {}, {}
        for (mode, name), v in now.items():
            k = norm_station(name)
            p0 = prev.get((mode, name))
            if not p0:
                continue
            a = bykey.setdefault(k, [0, 0]); a[0] += v; a[1] += p0
            disp.setdefault(k, re.sub(r"\s+(NR|LU|DLR|EL)$", "", name.strip()))
        for k, (v, p0) in bykey.items():
            loc = pts.get(k)
            if loc:
                out.append((loc[0], loc[1], v, p0, disp[k])); seen.add(k)
            else:
                unmatched += 1
    try:
        orr, span = orr_counts()
    except Exception:
        orr, span = {}, None
    for name, (v, p0) in orr.items():
        k = norm_station(name)
        if k in seen:
            continue
        loc = pts.get(k)
        if loc:
            out.append((loc[0], loc[1], v, p0, name)); seen.add(k)
    return out, {"tfl": label, "orr": span, "stations": len(out), "tfl_unmatched": unmatched}


# ---------- population ----------
def lsoa_points():
    """{LSOA21CD: (lat, lon)} for LSOAs in the London box, from ONS Open Geography."""
    p = CACHE / f"lsoa_centroids_{CITY}.json"
    if p.exists() and time.time() - p.stat().st_mtime < 180 * 86400:
        return json.loads(p.read_text())
    base = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LSOA_2021_EW_BSC_V4_RUC/FeatureServer/0/query"
    out, off = {}, 0
    while True:
        qs = urllib.parse.urlencode({"where": "1=1", "geometry": f"{LONDON[2]},{LONDON[0]},{LONDON[3]},{LONDON[1]}", "geometryType": "esriGeometryEnvelope",
                                     "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "LSOA21CD,LAT,LONG",
                                     "returnGeometry": "false", "f": "json", "resultOffset": off, "resultRecordCount": 2000})
        d = json.load(urllib.request.urlopen(urllib.request.Request(f"{base}?{qs}", headers=UA), timeout=120))
        feats = d.get("features", [])
        for f in feats:
            a = f["attributes"]
            if a.get("LAT") and a.get("LONG"):
                out[a["LSOA21CD"]] = (a["LAT"], a["LONG"])
        if len(feats) < 2000 and not d.get("exceededTransferLimit"):
            break
        off += len(feats)
    CACHE.mkdir(exist_ok=True); p.write_text(json.dumps(out))
    return out


def population_points():
    cents = lsoa_points()
    url = (f"https://www.nomisweb.co.uk/api/v01/dataset/NM_2014_1.data.csv?geography={cfg('nomis')}"
           "&date=latestMINUS3,latest&gender=0&c_age=200&measures=20100&select=date_name,geography_code,obs_value")
    f = fetch(url, f"nomis_lsoa_pop_{CITY}.csv", 30)
    pop = {}
    years = set()
    for r in csv.DictReader(open(f, encoding="utf-8-sig")):
        pop.setdefault(r["GEOGRAPHY_CODE"], {})[r["DATE_NAME"]] = num(r["OBS_VALUE"])
        years.add(r["DATE_NAME"])
    y0, y1 = min(years), max(years)
    out = [(cents[c][0], cents[c][1], v[y1], v[y0]) for c, v in pop.items()
           if c in cents and v.get(y0) and v.get(y1) and in_london(*cents[c])]
    return out, {"years": f"{y0}→{y1}", "lsoas": len(out)}


# ---------- house prices ----------
LONDON_POSTCODE_AREAS = ["e", "ec", "n", "nw", "se", "sw", "w", "wc", "br", "cr", "da", "en", "ha", "ig", "kt", "rm", "sm", "tw", "ub", "wd"]


def postcode_points():
    p = CACHE / f"postcodes_{CITY}.json"
    if p.exists() and time.time() - p.stat().st_mtime < 90 * 86400:
        return json.loads(p.read_text())
    z = zipfile.ZipFile(fetch("https://api.os.uk/downloads/v1/products/CodePointOpen/downloads?area=GB&format=CSV&redirect", "codepo_gb.zip", 90))
    out = {}
    for n in z.namelist():
        m = re.search(r"/([a-z]+)\.csv$", n)
        if not m or m.group(1) not in cfg("pc_areas"):
            continue
        for r in csv.reader(io.TextIOWrapper(z.open(n), encoding="utf-8")):
            E, N = num(r[2]), num(r[3])
            if E and N:
                lat, lon = bng_to_wgs84(E, N)
                if in_london(lat, lon):
                    out[r[0].replace(" ", "")] = (round(lat, 6), round(lon, 6))
    CACHE.mkdir(exist_ok=True); p.write_text(json.dumps(out))
    return out


def price_points(today=None):
    """Sales in Greater London over the 24 months to the latest recorded sale:
    (lat, lon, price, period, type, new_build) with period 1 = latest 12 months, 0 = the 12 months before; type D/S/T/F."""
    today = today or dt.date.today()
    pcs = postcode_points()
    base = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
    rows, latest = [], dt.date(1900, 1, 1)
    early = today - dt.timedelta(days=800)
    for y in sorted({early.year, early.year + 1, today.year}):
        try:
            f = fetch(f"{base}/pp-{y}.csv", f"pp-{y}.csv", 7 if y == today.year else 60)
        except OSError:
            continue
        for r in csv.reader(open(f, encoding="latin-1")):
            # columns: id, price, date, postcode, type, new, tenure, paon, saon, street, locality, town, district, county, ppd_cat, status
            if len(r) < 15 or r[13] not in cfg("county") or r[14] != "A" or r[4] == "O":
                continue
            d = dt.date.fromisoformat(r[2][:10])
            if d < early:
                continue
            loc = pcs.get(r[3].replace(" ", ""))
            if not loc:
                continue
            latest = max(latest, d)
            rows.append((loc[0], loc[1], float(r[1]), d, r[4], r[5] == "Y"))
    cut1, cut0 = latest - dt.timedelta(days=365), latest - dt.timedelta(days=730)
    out = [(a, b, pr, 1 if d > cut1 else 0, t, nb) for a, b, pr, d, t, nb in rows if d > cut0]
    return out, {"sales": len(out), "latest_sale": latest.isoformat(), "window": f"{cut0.isoformat()}→{latest.isoformat()}"}


# ---------- aggregation ----------
def aggregate(points, kind):
    """Per-tile summary; returns {tile: metric dict}."""
    acc = {}
    for p in points:
        acc.setdefault(tile(p[0], p[1]), []).append(p)
    return {t: summarise(v, kind) for t, v in acc.items()}


def within(points, lat, lon, r_km):
    return [p for p in points if abs(p[0] - lat) < 0.03 and km(lat, lon, p[0], p[1]) <= r_km]


def summarise(pts, kind):
    if kind in ("transport", "population"):
        now, before = sum(p[2] for p in pts), sum(p[3] for p in pts)
        out = {"growth": (now / before - 1) if before else None, "now": now, "before": before, "n": len(pts)}
        if kind == "transport":
            out["top"] = [[p[4], round(p[2]), round(p[3])] for p in sorted(pts, key=lambda p: -p[2])[:6]]
        return out
    if kind == "prices":
        # Mix-adjusted: median change within each property type (flat, terraced, semi, detached),
        # weighted by this year's sales of that type, so a shift in what sold doesn't look like a price move.
        a = [p[2] for p in pts if p[3] == 1]
        num_, den = 0.0, 0
        for t in "FTSD":
            # resales only: new-build launches carry a premium that distorts year-on-year comparisons
            now = [p[2] for p in pts if p[3] == 1 and p[4] == t and not p[5]]; was = [p[2] for p in pts if p[3] == 0 and p[4] == t and not p[5]]
            if len(now) >= 10 and len(was) >= 10:
                num_ += len(now) * (statistics.median(now) / statistics.median(was) - 1); den += len(now)
        resales = sum(1 for p in pts if p[3] == 1 and not p[5])
        ok = den >= 25 and den >= 0.6 * resales
        types = []
        for t, nm in (("F", "Flats"), ("T", "Terraced"), ("S", "Semi-detached"), ("D", "Detached")):
            now = [p[2] for p in pts if p[3] == 1 and p[4] == t and not p[5]]; was = [p[2] for p in pts if p[3] == 0 and p[4] == t and not p[5]]
            if now:
                types.append([nm, len(now), round(statistics.median(now)), round(statistics.median(was)) if len(was) >= 10 else None])
        return {"growth": num_ / den if ok else None, "median": statistics.median(a) if len(a) >= 25 else None,
                "sales": len(a), "n": len(pts), "new_build": sum(1 for p in pts if p[3] == 1 and p[5]), "types": types}
    raise ValueError(kind)


def load_all(today=None):
    """Returns {signal: (points, meta, kind)}; a source that fails is skipped (and reported) instead of breaking the index."""
    out, errors = {}, {}
    for name, fn, kind in (("transport", transport_points, "transport"), ("population", population_points, "population"),
                           ("prices", lambda: price_points(today), "prices")):
        try:
            pts, meta = fn()
            if pts:
                out[name] = (pts, meta, kind)
            else:
                errors[name] = "no data"
        except Exception as e:  # noqa: BLE001
            errors[name] = f"{type(e).__name__}: {e}"
    return out, errors
