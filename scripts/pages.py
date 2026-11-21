"""Build the public SEO pages from the public data files (run by publish.py every Monday).

Writes:
  london/index.html             all tracked London neighbourhoods
  london/<slug>/index.html      one page per neighbourhood (full detail for this week's public top 10;
                                the others show planning context only, so no paid data is published)
  class-ma/index.html           Class MA landing page for planning consultants and developers
  sitemap.xml, robots.txt

Only reads data/momentum.json (public top 10), data/classma.json and data/feed.json, which are already public.
Look and nav are copied from methodology.html, so re-run this after changing the site's styles or nav.
Run by hand: python3 scripts/pages.py
"""
import datetime as dt
import html
import json
import math
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://terrayne.co"
CF_BEACON = '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon=\'{"token": "ed3ce7710a55414f8f881c84da8964aa"}\'></script>'

# Every tracked neighbourhood (same order and names as AREAS in momentum.py), with its web address.
AREAS = [
    ("Nine Elms", "Nine Elms & Vauxhall", "LB Wandsworth / Lambeth", 51.4815, -0.1290, "nine-elms-vauxhall"),
    ("Stratford", "Stratford & Olympic Park", "LB Newham", 51.5416, -0.0034, "stratford"),
    ("Canada Water", "Canada Water & Surrey Quays", "LB Southwark", 51.4980, -0.0497, "canada-water"),
    ("Whitechapel", "Whitechapel & Aldgate", "LB Tower Hamlets", 51.5195, -0.0597, "whitechapel-aldgate"),
    ("King’s Cross", "King’s Cross & St Pancras", "LB Camden / Islington", 51.5347, -0.1246, "kings-cross"),
    ("Croydon", "Croydon town centre", "LB Croydon", 51.3762, -0.0982, "croydon"),
    ("Old Kent Road", "Old Kent Road", "LB Southwark", 51.4850, -0.0750, "old-kent-road"),
    ("Elephant", "Elephant & Castle", "LB Southwark / Lambeth", 51.4945, -0.1000, "elephant-and-castle"),
    ("Wembley", "Wembley Park", "LB Brent", 51.5600, -0.2795, "wembley-park"),
    ("Brent Cross", "Brent Cross & Cricklewood", "LB Barnet", 51.5700, -0.2200, "brent-cross"),
    ("Tottenham Hale", "Tottenham Hale", "LB Haringey", 51.5880, -0.0600, "tottenham-hale"),
    ("Ilford", "Ilford town centre", "LB Redbridge", 51.5590, 0.0700, "ilford"),
    ("Greenwich Pen.", "Greenwich Peninsula", "RB Greenwich", 51.4990, 0.0050, "greenwich-peninsula"),
    ("Woolwich", "Woolwich", "RB Greenwich", 51.4910, 0.0690, "woolwich"),
    ("Lewisham", "Lewisham town centre", "LB Lewisham", 51.4620, -0.0120, "lewisham"),
    ("Hammersmith", "Hammersmith & White City", "LB Hammersmith & Fulham", 51.5000, -0.2250, "hammersmith-white-city"),
    ("Ealing", "Ealing Broadway", "LB Ealing", 51.5130, -0.3010, "ealing"),
    ("Isle of Dogs", "Canary Wharf & Isle of Dogs", "LB Tower Hamlets", 51.5000, -0.0180, "canary-wharf-isle-of-dogs"),
]
SLUG = {a[0]: a[5] for a in AREAS}
TREND = {"u": ("Rising", "↑", "up"), "f": ("Stable", "→", "flat"), "d": ("Falling", "↓", "down")}
CONF = {"H": "High", "M": "Medium", "L": "Low"}

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def nf(v):
    return f"{round(v or 0):,}"


def pct(v, dp=1):
    if v is None:
        return "—"
    s = f"{abs(v) * 100:.{dp}f}%"
    return ("+" if v > 0 else "−" if v < 0 else "") + s


def pts(v):
    if not v:
        return "unchanged"
    return ("+" if v > 0 else "−") + f"{abs(v)} pts"


def day(iso):
    try:
        d = dt.date.fromisoformat(iso[:10])
    except Exception:  # noqa: BLE001
        try:
            d = dt.datetime.strptime(iso, "%d/%m/%Y").date()
        except Exception:  # noqa: BLE001
            return iso or ""
    return f"{d.day} {d.strftime('%B %Y')}"


def homes(a):
    """Net new homes proposed, as the homepage shows it (stored as text like '1,277')."""
    u = str(a.get("u") or "0").replace(",", "")
    try:
        return nf(float(u))
    except ValueError:
        return str(a.get("u"))


def verdict(s):
    return "Changing fast" if s >= 80 else "Changing" if s >= 65 else "Steady" if s >= 50 else "Quiet"


def tidy(site):
    """Council site names are often in capitals: 'DEVELOPMENT AT 222 High Road' -> 'Development At 222 High Road'."""
    return re.sub(r"\b([A-Z]{2,})\b", lambda m: m.group(1) if m.group(1) in ("UK", "NHS", "TFL") else m.group(1).capitalize(), site or "Site")


def km(a, b, c, d):
    return math.hypot((d - b) * 111.32 * math.cos((a + c) / 2 * math.pi / 180), (c - a) * 110.57)


def ref_link(ref, borough):
    q = f'"{ref}" {borough} council planning application'
    return e("https://www.google.com/search?q=" + urllib.parse.quote_plus(q))


def boroughs_of(b):
    """'LB Wandsworth / Lambeth' -> ['Wandsworth', 'Lambeth']"""
    b = re.sub(r"^(LB|RB)\s+", "", b)
    return [x.strip() for x in b.split("/")]


# ---------------------------------------------------------------- page shell (copied from methodology.html)

def shell():
    src = (ROOT / "methodology.html").read_text()
    head = src[:src.index("</head>")]
    head = re.sub(r"<title>.*?</title>\s*", "", head, flags=re.S)
    head = re.sub(r'<meta (name="description"|property="og:[^"]*"|name="twitter:[^"]*")[^>]*>\s*', "", head)
    head = re.sub(r'<link rel="canonical"[^>]*>\s*', "", head)
    nav = src[src.index("<nav>"):src.index("</nav>") + 6]
    nav_js = src[src.index("<script>", src.index("<footer")):]
    nav_js = nav_js[:nav_js.index("</script>") + 9]

    def absolute(t):
        t = re.sub(r'(href|src)="\./', r'\1="/', t)
        return re.sub(r'(href|src)="(?!https?:|/|#|mailto:|data:)([^"]+)"', r'\1="/\2"', t)

    return absolute(head), absolute(nav), nav_js


EXTRA_CSS = """<style>
.ap-h{padding:clamp(36px,7vh,76px) 0 8px}
.ap-h h1{font-size:clamp(36px,6.2vw,68px);max-width:980px;margin-bottom:18px}
.ap-lead{font-size:clamp(16px,2vw,19px);color:var(--mute);max-width:720px;margin:0 0 26px;line-height:1.6}
.crumb{font-size:13px;color:var(--mute);margin:0 0 22px}.crumb a{color:var(--accent)}.crumb a:hover{text-decoration:underline}
.ap-s{padding:clamp(34px,6vh,64px) 0}
.ap-s h2{font-size:clamp(26px,3.6vw,40px);margin-bottom:10px}
.ap-sub{color:var(--mute);max-width:680px;margin:0 0 22px;line-height:1.6}
.apc{background:rgba(13,24,48,.72);border:1px solid var(--line);border-radius:20px;padding:clamp(18px,2.6vw,26px);min-width:0}
.apg{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr);gap:18px}
.apg3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.kn{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.kn.k4{grid-template-columns:repeat(4,minmax(0,1fr))}
.kn .apc b{display:block;font-size:clamp(24px,3vw,30px);letter-spacing:-.02em;line-height:1.15}
.kn .apc span{display:block;color:var(--mute);font-size:13.5px;margin-top:6px;line-height:1.45}
.score{display:flex;align-items:baseline;gap:6px;margin:4px 0 10px}.score b{font-size:clamp(64px,9vw,92px);line-height:.95;letter-spacing:-.04em}.score span{color:var(--mute);font-size:18px}
.apt{display:inline-block;font-size:12.5px;letter-spacing:0;text-transform:none;border:1px solid var(--line);border-radius:999px;padding:4px 11px;margin:0 6px 8px 0;color:#c8d4e8}
.apt.hi{background:rgba(79,155,232,.16);border-color:rgba(79,155,232,.45);color:#cfe6ff}
.apt.up{color:#7ee0b5}.apt.down{color:#ffb38a}
.muted{color:var(--mute)}.small{font-size:13px;line-height:1.55}
.sg{display:grid;grid-template-columns:minmax(0,1fr) 54px 78px;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid rgba(28,43,77,.7);font-size:14.5px}
.sg:last-child{border-bottom:0}.sg .sgb{grid-column:1/-1;height:5px;background:#16264a;border-radius:9px;overflow:hidden;margin-top:-2px}.sg .sgb i{display:block;height:100%;background:linear-gradient(90deg,#3c7fd6,#5fd6b8);border-radius:9px}
.sg .sgv{text-align:right;font-variant-numeric:tabular-nums}.sg .sgt{text-align:right;font-size:12.5px;color:var(--mute)}.sg .sgt.up{color:#7ee0b5}.sg .sgt.down{color:#ffb38a}
.lst{list-style:none;margin:0;padding:0}.lst li{padding:14px 0;border-bottom:1px solid rgba(28,43,77,.7)}.lst li:last-child{border-bottom:0}
.lst b{display:block;font-size:15.5px;margin-bottom:3px}.lst p{margin:6px 0 0;color:#c8d4e8;font-size:14.5px;line-height:1.55}
.lst a.ref{display:inline-block;margin-top:6px;color:var(--accent);font-size:13px}.lst span.small{display:block}.lst a.ref:hover{text-decoration:underline}
.ap-cta{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}
.ap-t{width:100%;border-collapse:collapse;font-size:14.5px}.ap-t th{text-align:left;color:var(--mute);font-weight:500;font-size:12.5px;padding:0 10px 10px 0;border-bottom:1px solid var(--line)}
.ap-t td{padding:11px 10px 11px 0;border-bottom:1px solid rgba(28,43,77,.7)}.ap-t td.n,.ap-t th.n{text-align:right;font-variant-numeric:tabular-nums}
.apw{overflow-x:auto;-webkit-overflow-scrolling:touch}
.alist{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.alist a{display:block;background:rgba(13,24,48,.72);border:1px solid var(--line);border-radius:16px;padding:16px 18px;transition:border-color .2s}
.alist a:hover{border-color:#3a5a92}.alist a b{display:block;font-size:16px}.alist a span{display:block;color:var(--mute);font-size:13px;margin-top:3px}
.alist a em{font-style:normal;float:right;font-weight:700;font-size:20px;color:#fff}
.faq details{border-bottom:1px solid var(--line);padding:16px 0}.faq summary{cursor:pointer;font-size:16.5px;list-style:none;display:flex;justify-content:space-between;gap:16px}
.faq summary::-webkit-details-marker{display:none}.faq summary:after{content:"+";color:var(--mute)}.faq details[open] summary:after{content:"−"}
.faq details p{color:var(--mute);margin:10px 0 0;line-height:1.65;max-width:760px}
.lock{border:1px dashed #2f4677;background:rgba(13,24,48,.5)}
@media(max-width:820px){.apg{grid-template-columns:1fr}.kn,.kn.k4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.ap-t.stack thead{display:none}.ap-t.stack,.ap-t.stack tbody,.ap-t.stack tr,.ap-t.stack td{display:block;width:100%}
 .ap-t.stack tr{padding:12px 0;border-bottom:1px solid var(--line)}.ap-t.stack td{border:0;padding:2px 0;text-align:left}
 .ap-t.stack td[data-l]{display:inline-block!important;width:auto!important;font-family:inherit;letter-spacing:0;text-transform:none;margin:4px 14px 0 0;font-size:13px}.ap-t.stack td[data-l]:before{content:attr(data-l)": ";color:var(--mute)}
 .sg{grid-template-columns:minmax(0,1fr) 44px 70px;font-size:14px}}
</style>"""

DD_JS = """<script>(function(){var dd=document.getElementById("dd");if(!dd)return;var b=dd.querySelector("button");
b.onclick=function(e){e.stopPropagation();var o=dd.classList.toggle("open");b.setAttribute("aria-expanded",o)};
document.addEventListener("click",function(){dd.classList.remove("open");b.setAttribute("aria-expanded",false)})})();</script>"""


def footer():
    links = [("/about.html", "About"), ("/london/", "Neighbourhoods"), ("/class-ma/", "Class MA"), ("/planning.html", "Planning tracker"),
             ("/methodology.html", "Methodology"), ("/terms.html", "Terms"), ("/privacy.html", "Privacy")]
    return ('<footer><div class="wrap"><span>© 2026 Terrayne. Property intelligence.</span><span class="fl">'
            + "".join(f'<a href="{h}">{t}</a>' for h, t in links)
            + '<a class="tmark" href="#" aria-label="Back to top"><svg viewBox="0 0 270 143" aria-hidden="true"><path d="M0 40L270 0V46H0Z" fill="currentColor"/>'
            '<rect x="96" y="45" width="20" height="98" fill="currentColor"/></svg></a></span></div></footer>')


def page(title, desc, path, body, jsonld=None):
    head, nav, nav_js = shell()
    url = SITE + path
    meta = (f"<title>{e(title)}</title>\n<meta name=\"description\" content=\"{e(desc)}\">\n<link rel=\"canonical\" href=\"{url}\">\n"
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Terrayne"><meta property="og:title" content="{e(title)}">'
            f'<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og.png">'
            f'<meta name="twitter:card" content="summary_large_image">\n')
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n' if jsonld else ""
    head = head.replace('<meta name="viewport"', meta + '<meta name="viewport"', 1)
    return (f"{head}{EXTRA_CSS}\n{ld}</head>\n<body>\n{nav}\n<main>\n{body}\n</main>\n{footer()}\n{nav_js}\n{DD_JS}\n"
            f'<script src="/assets/track.js"></script><script src="/assets/brief.js"></script>\n{CF_BEACON}\n</body>\n</html>\n')


def faq_html(qs):
    return '<div class="faq">' + "".join(f"<details><summary>{e(q)}</summary><p>{a}</p></details>" for q, a in qs) + "</div>"


def faq_ld(qs):
    strip = lambda s: re.sub(r"<[^>]+>", "", html.unescape(s))
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": strip(a)}} for q, a in qs]}


def brief_box(area="", title="", sub=""):
    attrs = f' data-area="{e(area)}"' if area else ""
    attrs += f' data-title="{e(title)}"' if title else ""
    attrs += f' data-sub="{e(sub)}"' if sub else ""
    return f'<div data-brief-signup data-root="/"{attrs}></div>'


# ---------------------------------------------------------------- neighbourhood pages

def near_rows(feed, lat, lon, names, n=4):
    rows = [r for r in feed.get("rows", []) if r.get("lat") and km(lat, lon, r["lat"], r["lon"]) <= 2.5]
    if len(rows) < 2:
        rows = rows + [r for r in feed.get("rows", []) if r["borough"] in names and r not in rows]
    rows.sort(key=lambda r: r.get("valid", ""), reverse=True)
    return rows[:n]


def feed_list(rows):
    if not rows:
        return '<p class="muted">No significant new filings nearby in the last 60 days.</p>'
    out = []
    for r in rows:
        scale = " · ".join(x for x in [f"{nf(r['homes'])} homes" if r.get("homes", 0) > 0 else "",
                                        f"{nf(r['commercial_m2'])} m² commercial" if r.get("commercial_m2", 0) > 0 else ""] if x)
        out.append(f'<li><b>{e(tidy(r["site"]))}</b><span class="muted small">{e(r["borough"])} · filed {e(day(r["valid"]))}'
                   f'{" · " + e(scale) if scale else ""} · {e(r["status"])}</span><p>{e(r.get("why") or r.get("summary") or "")}</p>'
                   f'<a class="ref" href="{ref_link(r["ref"], r["borough"])}" target="_blank" rel="noopener">Search for ref {e(r["ref"])} ({e(r["borough"])} Council) →</a></li>')
    return '<ul class="lst">' + "".join(out) + "</ul>"


def classma_rows(cm, names):
    rows = [b for b in cm.get("boroughs", []) if b["borough"] in names]
    if not rows:
        return ""
    lines = []
    for b in rows:
        rate = f"{round(b['approval_rate'] * 100)}% approved" if b.get("approval_rate") is not None and b.get("decided_24m", 0) >= 5 else "too few decisions to rate"
        days = f", median decision {b['median_days']} days" if b.get("median_days") else ""
        lines.append(f"<li><b>{e(b['borough'])}</b><p>{nf(b['filed_12m'])} office-to-home (Class MA) applications in the last 12 months, "
                     f"proposing {nf(b['homes_12m'])} homes. {rate.capitalize()}{days}.</p></li>")
    return ('<div class="apc"><div class="eyebrow" style="margin-bottom:8px">Office-to-home conversions in the borough</div><ul class="lst">'
            + "".join(lines) + '</ul><p class="small muted" style="margin:12px 0 0"><a href="/class-ma/" style="color:var(--accent)">See every borough in the Class MA tracker →</a></p></div>')


def other_links(current):
    return '<div class="alist">' + "".join(
        f'<a href="/london/{a[5]}/"><b>{e(a[1])}</b><span>{e(a[2])}</span></a>' for a in sorted(AREAS, key=lambda a: a[1]) if a[0] != current) + "</div>"


def area_page(meta, a, rank, pub, cm, feed):
    short, full, borough, lat, lon, slug = meta
    names = boroughs_of(borough)
    upd = day(pub["generated"])
    near = near_rows(feed, lat, lon, names)
    radius = f"{pub.get('radius_km', 1.72):.1f}"
    crumb = f'<div class="crumb"><a href="/">Terrayne</a> › <a href="/london/">London neighbourhoods</a> › {e(full)}</div>'
    cta = (f'<div class="ap-cta"><a class="btn" href="/?q={e(short.replace("’", "").replace(".", ""))}#check">Check a postcode in {e(full)}</a>'
           f'<a class="btn ghost" href="/#compare">Compare with other areas</a></div>')
    if a:
        s, v = a["s"], verdict(a["s"])
        cf = a.get("cf") or ["M", []]
        tr = a.get("tr") or []
        off, raw = a.get("off") or {}, a.get("raw") or {}
        labels = pub["labels"]
        sig = "".join(
            f'<div class="sg"><span>{e(labels[i])}</span><span class="sgv">{x}</span>'
            f'<span class="sgt {TREND.get(tr[i] if i < len(tr) else "", ("", "", ""))[2]}">{TREND.get(tr[i] if i < len(tr) else "", ("", "", ""))[1]} {TREND.get(tr[i] if i < len(tr) else "", ("—", "", ""))[0]}</span>'
            f'<div class="sgb"><i style="width:{max(2, min(100, x or 0))}%"></i></div></div>'
            for i, x in enumerate(a.get("x", [])))
        kn = [(nf(raw.get("act")), "significant planning applications in the last 12 months"),
              (homes(a), "net new homes proposed"),
              (f"{nf(raw.get('com'))} m²", "net new commercial floorspace proposed")]
        if off.get("transport") is not None:
            kn.append((pct(off["transport"]), f"change in station use ({e(off.get('transport_span', ''))})"))
        if off.get("population") is not None:
            kn.append((pct(off["population"]), f"population change ({e(off.get('population_span', ''))})"))
        if off.get("median_price"):
            kn.append((f"£{nf(off['median_price'])}", f"median sale price, {pct(off.get('prices'))} on a year earlier"))
        schemes = a.get("schemes") or []
        sch = ('<ul class="lst">' + "".join(
            f'<li><b>{e(tidy(x["site"]))}</b><span class="muted small">{nf(x["units"]) + " homes · " if x.get("units", 0) > 0 else ""}'
            f'{e(x["status"])} · valid from {e(day(x.get("valid", "")))}</span>'
            f'<a class="ref" href="{ref_link(x["ref"], x["lpa"])}" target="_blank" rel="noopener">Search for ref {e(x["ref"])} ({e(x["lpa"])} Council) →</a></li>'
            for x in schemes[:6]) + "</ul>") if schemes else '<p class="muted">No large live schemes in the last 12 months.</p>'
        conf = f'Data confidence: {CONF.get(cf[0], "Medium")}' + (f" ({e('; '.join(cf[1]))})" if cf[1] else "")
        top = f"""<section class="ap-h"><div class="wrap">{crumb}
<div class="eyebrow">{e(borough)} · Updated {e(upd)}</div>
<h1>{e(full)}: what’s changing</h1>
<p class="ap-lead">Planning, new homes and property signals for the area within about {radius} km of {e(full)}, in plain English. Built from official data and updated every Monday.</p>
<div class="apg">
<div class="apc"><div class="eyebrow" style="margin-bottom:6px">Momentum Index</div>
<div class="score"><b>{s}</b><span>/100</span></div>
<span class="apt hi">{e(v)}</span><span class="apt {'up' if (a.get('c12') or 0) > 0 else 'down' if (a.get('c12') or 0) < 0 else ''}">{e(pts(a.get('c12')))} over 12 months</span>
<span class="apt">Ranked {rank} of {pub['tracked']} tracked London neighbourhoods</span><span class="apt">{conf}</span>
<p class="small muted" style="margin:10px 0 0">A score from 0 to 100 for how fast an area is changing compared with the rest of London, from seven signals. It measures activity, not where prices will go. Price headroom {a.get('hd', '—')}/100: cheaper than {a.get('hd', '—')}% of London. <a href="/methodology.html" style="color:var(--accent)">How the score works</a>.</p>
{cta}</div>
<div class="apc"><div class="eyebrow" style="margin-bottom:4px">The seven signals</div>{sig}
<p class="small muted" style="margin:10px 0 0">Arrows show the direction over the last 12 months.</p></div>
</div></div></section>
<section class="ap-s" style="padding-top:10px"><div class="wrap">
<h2>The numbers</h2>
<div class="kn">{''.join(f'<div class="apc"><b>{v_}</b><span>{l_}</span></div>' for v_, l_ in kn)}</div>
<div class="apc" style="margin-top:14px"><div class="eyebrow" style="margin-bottom:8px">In plain English</div><p style="margin:0;color:#c8d4e8;line-height:1.7">{e(a.get('t', ''))}</p></div>
</div></section>
<section class="ap-s"><div class="wrap{' apg' if near else ''}">
<div class="apc"><div class="eyebrow" style="margin-bottom:4px">Largest live schemes</div>{sch}</div>
{('<div class="apc"><div class="eyebrow" style="margin-bottom:4px">New filings nearby (last 60 days)</div>' + feed_list(near) + '</div>') if near else ''}
</div></section>"""
        qs = [(f"Is {full} changing?",
               f"{full} scores {s}/100 on Terrayne’s Momentum Index this week ({v.lower()}), ranked {rank} of {pub['tracked']} tracked London neighbourhoods, "
               f"and {pts(a.get('c12'))} over the last 12 months. In the last 12 months there were {nf(raw.get('act'))} significant planning applications "
               f"within about {radius} km of the centre."),
              (f"How many new homes are planned in {full}?",
               f"Significant planning applications in the last 12 months propose {homes(a)} net new homes within about {radius} km of {full}, "
               f"along with {nf(raw.get('com'))} m² of net new commercial floorspace. Figures come from the GLA Planning London Datahub."),
              ("Where does this data come from?",
               "Planning applications from the GLA Planning London Datahub, station use from TfL and the Office of Rail and Road, population from the ONS and "
               "sale prices from HM Land Registry. It’s updated every Monday by 7am UK time. Scores describe activity, not future prices, and aren’t investment advice.")]
        desc = (f"{full} scores {s}/100 on Terrayne’s Momentum Index: {nf(raw.get('act'))} significant planning applications and "
                f"{homes(a)} net new homes proposed in the last 12 months. Updated {upd}.")
    else:
        top = f"""<section class="ap-h"><div class="wrap">{crumb}
<div class="eyebrow">{e(borough)} · Updated {e(upd)}</div>
<h1>{e(full)}: what’s changing</h1>
<p class="ap-lead">Planning, new homes and property signals for {e(full)}, in plain English. Built from official data and updated every Monday.</p>
<div class="apg">
<div class="apc lock"><div class="eyebrow" style="margin-bottom:8px">Momentum Index</div>
<h2 style="font-size:clamp(22px,3vw,30px)">Outside this week’s top 10.</h2>
<p class="muted" style="margin:0">{e(full)} is one of {pub['tracked']} London neighbourhoods Terrayne tracks. This week it isn’t in the free top 10, so its score, the seven signals behind it, its 12-month trend and the largest schemes driving it are included with Pro.</p>
<div class="ap-cta"><a class="btn" href="/account.html?signup&amp;plan=pro">Get Pro, £29 a month</a><a class="btn ghost" href="/london/">See this week’s top 10</a></div></div>
<div class="apc"><div class="eyebrow" style="margin-bottom:4px">New filings nearby (last 60 days)</div>{feed_list(near)}</div>
</div>{cta}</div></section>"""
        qs = [(f"Is {full} changing?",
               f"{full} is one of {pub['tracked']} London neighbourhoods Terrayne tracks. This week it’s outside the free top 10; its full score and trend are in Pro. "
               f"You can check any postcode in the area free, up to 3 times a month."),
              ("Where does this data come from?",
               "Planning applications from the GLA Planning London Datahub, station use from TfL and the Office of Rail and Road, population from the ONS and "
               "sale prices from HM Land Registry. It’s updated every Monday by 7am UK time.")]
        desc = f"What’s being planned and built in {full} ({borough}): new planning filings, office-to-home conversions and property signals from official data. Updated {upd}."
    cmh = classma_rows(cm, names)
    body = f"""{top}
<section class="ap-s"><div class="wrap">
{brief_box(short)}
{('<div style="margin-top:18px">' + cmh + '</div>') if cmh else ''}
</div></section>
<section class="ap-s"><div class="wrap">
<h2>Questions about {e(full)}</h2>{faq_html(qs)}
</div></section>
<section class="ap-s"><div class="wrap">
<h2>Other London neighbourhoods</h2><p class="ap-sub">Terrayne tracks {pub['tracked']} of London’s fastest-changing neighbourhoods. Check any London postcode free on the <a href="/#check" style="color:var(--accent)">homepage</a>.</p>
{other_links(short)}
<p class="small muted" style="margin-top:26px">Sources: GLA Planning London Datahub, TfL, Office of Rail and Road, ONS and HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0. Statuses can change, so check the council record by reference. Scores describe activity, not future prices, and aren’t investment advice.</p>
</div></section>"""
    title = f"{full} regeneration and planning: what’s changing | Terrayne"
    return page(title, desc, f"/london/{slug}/", body, faq_ld(qs))


def london_page(pub):
    by = {a["n"]: a for a in pub["areas"]}
    top = sorted(pub["areas"], key=lambda a: -a["s"])
    cards = "".join(f'<a href="/london/{SLUG.get(a["n"], "")}/"><em>{a["s"]}</em><b>{e(a["f"])}</b><span>{e(a["b"])} · {e(verdict(a["s"]))} · {e(pts(a.get("c12")))} in 12 months</span></a>'
                    for a in top if a["n"] in SLUG)
    rest = "".join(f'<a href="/london/{m[5]}/"><b>{e(m[1])}</b><span>{e(m[2])} · score in Pro</span></a>' for m in sorted(AREAS, key=lambda m: m[1]) if m[0] not in by)
    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › London neighbourhoods</div>
<div class="eyebrow">Updated {e(day(pub['generated']))}</div>
<h1>London neighbourhoods: where change is coming.</h1>
<p class="ap-lead">Terrayne tracks {pub['tracked']} of London’s fastest-changing neighbourhoods, scoring each from 0 to 100 on how fast it is changing, from planning filings, station use, population and sale prices. Here are this week’s top 10, free.</p>
<div class="ap-cta"><a class="btn" href="/#check">Check any London postcode</a><a class="btn ghost" href="/#compare">Compare areas side by side</a></div>
</div></section>
<section class="ap-s" style="padding-top:20px"><div class="wrap">
<h2>This week’s top 10</h2><p class="ap-sub">Scores out of 100. A high score means more is changing, not that prices will rise. <a href="/methodology.html" style="color:var(--accent)">How the score works</a>.</p>
<div class="alist">{cards}</div>
<h2 style="margin-top:44px">Also tracked</h2><p class="ap-sub">Their scores, signals and trends are included with Pro. Each page shows new planning filings nearby.</p>
<div class="alist">{rest}</div>
</div></section>
<section class="ap-s"><div class="wrap">{brief_box()}</div></section>"""
    return page("London neighbourhoods: regeneration and planning, area by area | Terrayne",
                f"Which London neighbourhoods are changing fastest? Terrayne scores {pub['tracked']} areas every week from planning filings, station use, population and sale prices.",
                "/london/", body)


# ---------------------------------------------------------------- Class MA landing page

def classma_page(cm):
    L = cm.get("london", {})
    upd = day(cm.get("generated", ""))
    rows = "".join(
        f'<tr><td><b>{e(b["borough"])}</b></td><td class="n" data-l="Filed (12m)">{nf(b["filed_12m"])}</td><td class="n" data-l="Homes">{nf(b["homes_12m"])}</td>'
        f'<td class="n" data-l="Approved">{(str(round(b["approval_rate"] * 100)) + "%") if b.get("approval_rate") is not None and b.get("decided_24m", 0) >= 5 else "—"}</td>'
        f'<td class="n" data-l="Median decision">{(str(b["median_days"]) + " days") if b.get("median_days") else "—"}</td><td class="n" data-l="Pending">{nf(b.get("pending", 0))}</td></tr>'
        for b in cm.get("boroughs", []))
    latest = "".join(
        f'<li><b>{e(tidy(r["site"]))}</b><span class="muted small">{e(r["borough"])} · filed {e(day(r["valid"]))} · '
        f'{nf(r["homes"]) + " homes · " if r.get("homes", 0) > 0 else ""}{e(r["status"])}</span>'
        f'<a class="ref" href="{ref_link(r["ref"], r["borough"])}" target="_blank" rel="noopener">Search for ref {e(r["ref"])} ({e(r["borough"])} Council) →</a></li>'
        for r in cm.get("latest", [])[:8])
    uses = [("Advise on the odds", "Approval rates for office-to-home conversions in every London borough, so you can tell a client how a council has treated similar applications before you take the job on."),
            ("Set expectations on timing", "Median decision times against the 56-day limit, borough by borough, so your programme and your client’s finance line up with reality."),
            ("Hear about new filings first", "Save the sites and patches you work on. Every new Class MA application within a 5, 10 or 20-minute walk lands in your Monday brief by 7am."),
            ("Find the council record fast", "Every filing comes with its council reference and a direct search link, so you can pull up comparable decisions in seconds.")]
    qs = [("What is Class MA?",
           "Class MA is a permitted development right in England that lets buildings in commercial, business and service use (Class E), such as offices and shops, become homes "
           "through prior approval instead of a full planning application. The council can only consider a limited set of matters, such as transport, contamination, flooding, "
           "noise and natural light."),
          ("What is the 56-day limit?",
           "Councils have 56 days to decide a prior approval application. If they don’t decide in time, the developer can usually go ahead, so decision times matter a lot for programmes."),
          ("How is the approval rate worked out?",
           "It counts approvals and “prior approval not required” decisions against refusals over the last 24 months, and is only shown where at least 5 applications were decided. "
           "Some boroughs record Class MA under other application types, so their counts may look low."),
          ("How up to date is it?",
           "Councils add applications to the GLA’s Planning London Datahub every day. Terrayne collects and processes them early every Monday, and everything is updated by 7am UK time."),
          ("What do I get free, and what’s in Pro?",
           "The borough table and the latest filings are free, with no account. Pro (£29 a month) adds alerts for new filings near the sites you save, the Monday brief, the full "
           "planning signal feed with “why it matters”, unlimited postcode checks and PDF reports. Team (£99 a month) covers up to 5 people.")]
    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › Class MA tracker</div>
<div class="eyebrow">For planning consultants and developers · Updated {e(upd)}</div>
<h1>Class MA approvals, borough by borough.</h1>
<p class="ap-lead">See where office-to-home conversions get approved, how long each London council takes to decide, and every new Class MA filing, without trawling 33 planning portals. Updated every Monday from the GLA Planning London Datahub.</p>
<div class="ap-cta"><a class="btn" href="/account.html?signup" data-ev="signup_click" data-evd="class-ma hero">Start free</a><a class="btn ghost" href="#boroughs">See the borough table</a></div>
</div></section>
<section class="ap-s" style="padding-top:20px"><div class="wrap">
<div class="kn k4">
<div class="apc"><b>{nf(L.get('filed_12m'))}</b><span>Class MA applications in London, last 12 months</span></div>
<div class="apc"><b>{nf(L.get('homes_12m'))}</b><span>homes proposed through them</span></div>
<div class="apc"><b>{round((L.get('approval_rate') or 0) * 100)}%</b><span>approved, of those decided in the last 24 months</span></div>
<div class="apc"><b>{L.get('median_days', '—')} days</b><span>median decision time (legal limit: 56)</span></div>
</div></div></section>
<section class="ap-s"><div class="wrap">
<h2>How consultants use it</h2><p class="ap-sub">Built for people who advise on office-to-home schemes, or buy buildings for them.</p>
<div class="apg3">{''.join(f'<div class="apc"><b style="display:block;font-size:17px;margin-bottom:6px">{e(t)}</b><span class="muted" style="font-size:14.5px;line-height:1.6">{e(d)}</span></div>' for t, d in uses)}</div>
</div></section>
<section class="ap-s" id="boroughs"><div class="wrap">
<h2>Every London borough</h2><p class="ap-sub">Sorted by applications filed in the last 12 months. Approval rate and decision time cover the last 24 months, shown where at least 5 were decided.</p>
<div class="apc apw"><table class="ap-t stack"><thead><tr><th>Borough</th><th class="n">Filed (12m)</th><th class="n">Homes</th><th class="n">Approved</th><th class="n">Median decision</th><th class="n">Pending</th></tr></thead><tbody>{rows}</tbody></table></div>
</div></section>
<section class="ap-s"><div class="wrap">
<div class="apc" style="margin-bottom:18px"><div class="eyebrow" style="margin-bottom:4px">Latest Class MA filings</div><ul class="lst">{latest}</ul>
<p class="small muted" style="margin:12px 0 0"><a href="/planning.html" style="color:var(--accent)">See the full planning tracker →</a></p></div>
{brief_box(title="See a real Monday brief first.", sub="Pick a neighbourhood and we’ll email you this week’s brief, including new office-to-home filings nearby. No account or card needed.")}
</div></section>
<section class="ap-s"><div class="wrap">
<div class="apc" style="text-align:center;padding:clamp(26px,4vw,44px)">
<h2 style="font-size:clamp(26px,3.6vw,38px)">Get new Class MA filings near your sites, every Monday.</h2>
<p class="ap-sub" style="margin:0 auto 6px">Pro is £29 a month, or £290 a year. Cancel any time. Team is £99 a month for up to 5 people.</p>
<div class="ap-cta" style="justify-content:center"><a class="btn" href="/account.html?signup&amp;plan=pro">Get Pro</a><a class="btn ghost" href="/account.html?signup">Start free</a>
<a class="btn ghost" href="mailto:hello@terrayne.co?subject=Terrayne%20walkthrough" data-ev="demo_click">Book a 15-minute walkthrough</a></div></div>
</div></section>
<section class="ap-s"><div class="wrap"><h2>Questions</h2>{faq_html(qs)}
<p class="small muted" style="margin-top:22px">Source: GLA Planning London Datahub. Contains public sector information licensed under the Open Government Licence v3.0. Statuses can change, so check the council record by reference. Not legal or planning advice.</p></div></section>"""
    return page("Class MA tracker: London office-to-home approvals by borough | Terrayne",
                f"Class MA approval rates and decision times for every London borough, plus every new office-to-home filing. {nf(L.get('filed_12m'))} applications in the last 12 months. Updated {upd}.",
                "/class-ma/", body, faq_ld(qs))


# ---------------------------------------------------------------- write everything

def write_all():
    pub = json.loads((ROOT / "data" / "momentum.json").read_text())
    cm = json.loads((ROOT / "data" / "classma.json").read_text())
    feed = json.loads((ROOT / "data" / "feed.json").read_text())
    by = {a["n"]: a for a in pub["areas"]}
    ranked = [a["n"] for a in sorted(pub["areas"], key=lambda a: -a["s"])]
    for m in AREAS:
        d = ROOT / "london" / m[5]
        d.mkdir(parents=True, exist_ok=True)
        a = by.get(m[0])
        (d / "index.html").write_text(area_page(m, a, ranked.index(m[0]) + 1 if a else None, pub, cm, feed))
    (ROOT / "london" / "index.html").write_text(london_page(pub))
    (ROOT / "class-ma").mkdir(exist_ok=True)
    (ROOT / "class-ma" / "index.html").write_text(classma_page(cm))
    lastmod = pub["generated"]
    urls = ["/", "/class-ma/", "/london/", "/planning.html", "/methodology.html", "/about.html", "/report.html"] + [f"/london/{m[5]}/" for m in AREAS]
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + "".join(f"  <url><loc>{SITE}{u}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    (ROOT / "robots.txt").write_text("User-agent: *\nDisallow: /admin.html\nDisallow: /account.html\nDisallow: /unsubscribe.html\n\n"
                                     f"Sitemap: {SITE}/sitemap.xml\n")
    return {"area_pages": len(AREAS), "with_scores": len(by), "sitemap_urls": len(urls)}


if __name__ == "__main__":
    print(write_all())
