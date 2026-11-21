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
.kn .apc span{display:block;color:var(--mute);font-size:13.5px;margin-top:6px;line-height:1.45}.kn .apc em{display:block;font-style:normal;color:#9fd0ff;font-size:12.5px;margin-top:8px}
.sgh{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#9fd0ff;margin:16px 0 2px}.sgh:first-of-type{margin-top:8px}.sgh span{letter-spacing:0;text-transform:none;color:var(--mute);margin-left:6px}
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
.apg2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.lb td{vertical-align:middle}.lb .rk{color:var(--mute);width:28px}.lb a.nm b{font-size:15.5px}.lb a.nm:hover b{text-decoration:underline}.lb td span.small{display:block}
.lb td.up{color:#7ee0b5}.lb td.down{color:#ffb38a}
.scb{display:flex;align-items:center;gap:10px;min-width:130px}.scb b{font-size:20px;font-variant-numeric:tabular-nums;width:30px}.scb i{flex:1;height:6px;background:#16264a;border-radius:9px;overflow:hidden;min-width:60px}.scb u{display:block;height:100%;border-radius:9px}
.mvr{display:block;transition:border-color .2s}.mvr:hover{border-color:#3a5a92}.mvr .eyebrow{display:block;font-size:11px;margin-bottom:8px}.kn .mvr b{font-size:clamp(18px,2.2vw,22px)}
.alist.one{grid-template-columns:1fr}
.lb .rkm{display:none}
.sgx{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid rgba(28,43,77,.7)}.sgx:last-of-type{border-bottom:0}.sgx b{display:block;font-size:15px}.sgx span{display:block;color:var(--mute);font-size:13.5px;line-height:1.5;margin-top:3px}.sgx em{font-style:normal;font-weight:700;font-size:18px;color:#9fd0ff;font-variant-numeric:tabular-nums}
.vlist{list-style:none;padding:0;margin:10px 0 0}.vlist li{display:flex;align-items:center;gap:10px;padding:5px 0;font-size:14px;color:#c8d4e8}.vlist i{width:10px;height:10px;border-radius:50%;flex:none}.vlist b{width:74px;color:#fff;font-variant-numeric:tabular-nums}
.bth{font-size:clamp(18px,2.2vw,22px);margin:8px 0 6px;line-height:1.3}
.btb{display:grid;grid-template-columns:110px minmax(0,1fr) 62px;gap:10px;align-items:center;font-size:14px;padding:6px 0}.btb span{color:#c8d4e8}.btb i{height:8px;background:#16264a;border-radius:9px;overflow:hidden}.btb u{display:block;height:100%;background:linear-gradient(90deg,#3c7fd6,#5fd6b8);border-radius:9px}.btb b{text-align:right;font-variant-numeric:tabular-nums}
.ix-plans{display:flex;justify-content:space-between;align-items:center;gap:22px;flex-wrap:wrap;background:linear-gradient(135deg,rgba(30,64,120,.45),rgba(13,24,48,.8))}
.ixmap{padding:8px;position:relative;overflow:hidden}
.wk{margin:16px 0 4px;border-color:#2f4677;background:linear-gradient(135deg,rgba(30,64,120,.35),rgba(13,24,48,.75))}.wk p{margin:8px 0 0;font-size:clamp(15.5px,1.8vw,17.5px);line-height:1.65;color:#e3ebf7}
.lb td.tr{padding-right:0}.spk{display:block}
.ldrs{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}.ldr{display:block;transition:border-color .2s}.ldr:hover{border-color:#3a5a92}
.ldr .eyebrow{display:block;font-size:11px;margin-bottom:8px}.ldr b{display:block;font-size:18px}.ldr span{display:block;color:#c8d4e8;font-size:14px;margin-top:4px}.ldr em{display:block;font-style:normal;color:var(--mute);font-size:12.5px;margin-top:8px}
.cite{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.cite code{display:block;margin-top:10px;font-size:13px;color:#9fd0ff;background:#081227;border:1px solid var(--line);border-radius:10px;padding:9px 12px;white-space:normal}
.hm .hc{transition:opacity .15s,stroke .15s;stroke:transparent;stroke-width:2}.hm .hcells:hover .hc{opacity:.55}.hm .hcells .hc:hover{opacity:1;stroke:#fff}
.hm .mk{cursor:pointer}.hm .mk:hover text{text-decoration:underline}
.htip{position:absolute;pointer-events:none;opacity:0;transition:opacity .12s;background:#0d1830;border:1px solid #2f4677;color:#fff;font-size:12.5px;padding:7px 10px;border-radius:10px;max-width:230px;box-shadow:0 8px 24px rgba(0,0,0,.4)}
.hsum{margin-top:16px}.hleg{display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--mute)}.hleg i{flex:0 1 260px;height:8px;border-radius:9px;background:linear-gradient(90deg,rgb(16,28,56),rgb(30,62,120) 38%,rgb(44,102,186) 58%,rgb(66,150,230) 72%,rgb(95,214,184) 85%,rgb(200,250,232))}
.hbar{display:flex;height:12px;border-radius:9px;overflow:hidden;margin:14px 0 10px;gap:2px}.hbar i{display:block;height:100%}
.hkeys{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13.5px;color:#c8d4e8}.hkeys u{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
@media(max-width:820px){.apg,.apg2{grid-template-columns:1fr}.kn,.kn.k4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.ap-t.stack thead{display:none}.ap-t.stack,.ap-t.stack tbody,.ap-t.stack tr,.ap-t.stack td{display:block;width:100%}
 .ap-t.stack tr{padding:12px 0;border-bottom:1px solid var(--line)}.ap-t.stack td{border:0;padding:2px 0;text-align:left}
 .ap-t.stack td[data-l]{display:inline-block!important;width:auto!important;font-family:inherit;letter-spacing:0;text-transform:none;margin:4px 14px 0 0;font-size:13px}.ap-t.stack td[data-l]:before{content:attr(data-l)": ";color:var(--mute)}
 .sg{grid-template-columns:minmax(0,1fr) 44px 70px;font-size:14px}
 .hm .lk text{display:none}.hm text{font-size:30px}.hm .mk circle{r:11px}
 .lb td.rk{display:none!important}.lb .rkm{display:inline}.lb td[data-l="Score"]{display:block!important;margin:6px 0 2px!important}.lb td[data-l="Score"]:before{content:none!important}.scb{max-width:260px}}
</style>"""

DD_JS = """<script>(function(){var dd=document.getElementById("dd");if(!dd)return;var b=dd.querySelector("button");
b.onclick=function(e){e.stopPropagation();var o=dd.classList.toggle("open");b.setAttribute("aria-expanded",o)};
document.addEventListener("click",function(){dd.classList.remove("open");b.setAttribute("aria-expanded",false)})})();</script>"""


def footer():
    links = [("/about.html", "About"), ("/london/", "Momentum Index"), ("/class-ma/", "Class MA"), ("/planning.html", "Planning tracker"),
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
    crumb = f'<div class="crumb"><a href="/">Terrayne</a> › <a href="/london/">Momentum Index</a> › {e(full)}</div>'
    cta = (f'<div class="ap-cta"><a class="btn" href="/?q={e(short.replace("’", "").replace(".", ""))}#check">Check a postcode in {e(full)}</a>'
           f'<a class="btn ghost" href="/#compare">Compare with other areas</a></div>')
    if a:
        s, v = a["s"], verdict(a["s"])
        cf = a.get("cf") or ["M", []]
        tr = a.get("tr") or []
        off, raw = a.get("off") or {}, a.get("raw") or {}
        labels = pub["labels"]
        def sgrow(i, x):
            k = tr[i] if i < len(tr) else ""
            return (f'<div class="sg"><span>{e(labels[i])}</span><span class="sgv">{x}</span>'
                    f'<span class="sgt {TREND.get(k, ("", "", ""))[2]}">{TREND.get(k, ("", "", ""))[1]} {TREND.get(k, ("—", "", ""))[0]}</span>'
                    f'<div class="sgb"><i style="width:{max(2, min(100, x or 0))}%"></i></div></div>')
        xs = a.get("x", [])
        sig = ('<div class="sgh">What’s coming <span>planning filings, last 12 months</span></div>' + "".join(sgrow(i, x) for i, x in enumerate(xs[:4]))
               + '<div class="sgh">What’s already changing <span>official statistics</span></div>' + "".join(sgrow(i + 4, x) for i, x in enumerate(xs[4:])))
        B = pub.get("bench") or {}
        typ = lambda v: f'<em>Typical London area: {v}</em>'
        kn = [(nf(raw.get("act")), "significant planning applications in the last 12 months" + (typ(nf(B["act"])) if "act" in B else "")),
              (homes(a), "net new homes proposed" + (typ(nf(B["pipe"])) if "pipe" in B else "")),
              (f"{nf(raw.get('com'))} m²", "net new commercial floorspace proposed" + (typ(nf(B["com"]) + " m²") if "com" in B else ""))]
        if off.get("transport") is not None:
            kn.append((pct(off["transport"]), f"change in station use ({e(off.get('transport_span', ''))})" + (typ(pct(B["transport"])) if "transport" in B else "")))
        if off.get("population") is not None:
            kn.append((pct(off["population"]), f"population change ({e(off.get('population_span', ''))})" + (typ(pct(B["population"])) if "population" in B else "")))
        if off.get("median_price"):
            kn.append((f"£{nf(off['median_price'])}", f"median sale price, {pct(off.get('prices'))} on a year earlier" + (typ("£" + nf(B["price_level"])) if "price_level" in B else "")))
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
<p class="small muted" style="margin:10px 0 0">Arrows show the direction over the last 12 months. Applications aren’t approvals: <a href="/methodology.html#signals" style="color:var(--accent)">what each signal tells you</a>.</p></div>
</div></div></section>
<section class="ap-s" style="padding-top:10px"><div class="wrap">
<h2>The numbers</h2><p class="ap-sub">Each figure is for the area within about {radius} km of the centre, next to the median for every same-sized area of London.</p>
<div class="kn">{''.join(f'<div class="apc"><b>{v_}</b><span>{l_}</span></div>' for v_, l_ in kn)}</div>
<div class="apc" style="margin-top:14px"><div class="eyebrow" style="margin-bottom:8px">In plain English</div><p style="margin:0;color:#c8d4e8;line-height:1.7">{e(a.get('t', ''))}</p></div>
</div></section>
<section class="ap-s"><div class="wrap{' apg' if near else ''}">
<div class="apc"><div class="eyebrow" style="margin-bottom:4px">Largest live schemes</div>{sch}</div>
{('<div class="apc"><div class="eyebrow" style="margin-bottom:4px">New filings nearby (last 60 days)</div>' + feed_list(near) + '</div>') if near else ''}
</div></section>"""
        qs = [(f"Is {full} changing?",
               f"{full} scores {s}/100 on Terrayne’s Momentum Index this week ({v.lower()}), ranked {rank} of {pub['tracked']} tracked London neighbourhoods, "
               f"and {('unchanged' if not a.get('c12') else ('up ' if a['c12'] > 0 else 'down ') + str(abs(a['c12'])) + ' pts')} over the past year. In the last 12 months there were {nf(raw.get('act'))} significant planning applications "
               f"within about {radius} km of the centre" + (f", against {nf(pub['bench']['act'])} for a typical same-sized area of London." if pub.get('bench', {}).get('act') else ".")),
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
<p class="small muted" style="margin-top:26px">Sources: GLA Planning London Datahub, TfL, Office of Rail and Road, ONS and HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0. Powered by TfL Open Data. Contains OS, Royal Mail, National Statistics and HM Land Registry data © copyright and database right 2026 (<a href="/methodology.html#sources" style="color:inherit;text-decoration:underline">full data credits</a>). Statuses can change, so check the council record by reference. Scores describe activity, not future prices, and aren’t investment advice.</p>
</div></section>"""
    title = f"{full} regeneration and planning: what’s changing | Terrayne"
    return page(title, desc, f"/london/{slug}/", body, faq_ld(qs))


VCOL = {"Changing fast": "#4f9be8", "Changing": "#5fd6b8", "Steady": "#9aa3b5", "Quiet": "#8c9ab3"}
SIGNAL_INFO = {
    "act": ("Significant planning applications", "How many sizeable applications (new homes, conversions, commercial space) were filed nearby in 12 months."),
    "pipe": ("Net new homes proposed", "Homes proposed minus homes lost, in applications that are still live."),
    "ma": ("Office-to-home conversions", "Homes proposed through Class MA prior approvals: offices and shops becoming flats."),
    "com": ("Net new commercial floorspace", "Square metres of shops, offices and other commercial space gained, minus space lost."),
    "transport": ("Station use", "Change in entries and exits at nearby stations, from TfL and the Office of Rail and Road."),
    "population": ("Population growth", "Change in residents across the small census areas (LSOAs) nearby, from the ONS."),
    "prices": ("Price momentum", "Year-on-year change in resale prices, like-for-like by property type, from HM Land Registry."),
}


def thames():
    """The river line used on the homepage map, so both maps match."""
    try:
        m = re.search(r"var TH=(\[\[.*?\]\]);", (ROOT / "index.html").read_text())
        return json.loads(m.group(1)) if m else []
    except (OSError, ValueError):
        return []


# Spread over 20-85, where London's squares actually sit, so differences show (same blues and teal as the homepage).
HSTOPS = [(20, (16, 28, 56)), (45, (30, 62, 120)), (58, (44, 102, 186)), (67, (66, 150, 230)), (75, (95, 214, 184)), (85, (200, 250, 232))]


def hcol(v):
    """Same colour scale as the homepage heat map."""
    a, b = HSTOPS[0], HSTOPS[-1]
    for i in range(len(HSTOPS) - 1):
        if HSTOPS[i][0] <= v <= HSTOPS[i + 1][0]:
            a, b = HSTOPS[i], HSTOPS[i + 1]
            break
    if v < HSTOPS[0][0]:
        b = a
    if v > b[0]:
        a = b
    t = 0 if a is b else (v - a[0]) / (b[0] - a[0])
    return "rgb(" + ",".join(str(round(c + (d - c) * t)) for c, d in zip(a[1], b[1])) + ")"


def _merc(lat, lon, z=13):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


# Label positions for the crowded centre of the map (dx, dy, anchor), so names don't overlap.
NUDGE = {"Elephant": (0, -15, "middle"), "Hammersmith": (-13, 5, "end"), "Nine Elms": (-14, 18, "end"), "Old Kent Road": (14, 20, "start"), "Canada Water": (12, -12, "start"),
         "Whitechapel": (14, -10, "start"), "King’s Cross": (-14, -10, "end"), "Isle of Dogs": (12, 20, "start"), "Greenwich Pen.": (12, -4, "start"),
         "Woolwich": (12, 16, "start"), "Lewisham": (12, 18, "start")}


def tile_data():
    try:
        return json.loads((ROOT / "data" / "tiles.json").read_text()).get("tiles", {})
    except (OSError, ValueError):
        return {}


def london_map(pub):
    """A heat map of every scored map square in London (the public data/tiles.json the homepage map uses), with the tracked neighbourhoods on top."""
    tiles = tile_data()
    by = {a["n"]: a for a in pub["areas"]}
    if not tiles:
        return ""
    ks = [(int(k.split("/")[1]), int(k.split("/")[2]), v) for k, v in tiles.items()]
    x0, x1 = min(k[0] for k in ks) - 0.6, max(k[0] for k in ks) + 1.6
    y0, y1 = min(k[1] for k in ks) - 0.6, max(k[1] for k in ks) + 1.6
    S = 1100 / (x1 - x0)
    W, H = 1100, (y1 - y0) * S
    P = lambda x, y: ((x - x0) * S, (y - y0) * S)
    out = [f'<svg class="hm" viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Heat map of the Momentum Index across London" style="width:100%;height:auto;display:block">',
           '<defs><filter id="hglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="22"/></filter>'
           '</defs>',
           f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" rx="18" fill="#060f22"/>']
    glow = []
    cells = []
    for x, y, v in ks:
        s = v.get("s", 0)
        px, py = P(x, y)
        glow.append(f'<rect x="{px - S * .15:.1f}" y="{py - S * .15:.1f}" width="{S * 1.3:.1f}" height="{S * 1.3:.1f}" fill="{hcol(s)}"/>')
        cf = CONF.get((v.get("cf") or ["M"])[0], "Medium")
        tr = v.get("c12")
        tip = f"{s}/100 · {verdict(s)}" + (f" · {'+' if tr > 0 else '−' if tr < 0 else '±'}{abs(tr)} pts in 12 months" if tr is not None else "") + f" · {cf} confidence"
        cells.append(f'<rect class="hc" data-t="{e(tip)}" x="{px + 1.2:.1f}" y="{py + 1.2:.1f}" width="{S - 2.4:.1f}" height="{S - 2.4:.1f}" rx="{S * .12:.1f}" '
                     f'fill="{hcol(s)}"><title>{e(tip)}</title></rect>')
    out.append(f'<g filter="url(#hglow)" opacity=".55">{"".join(glow)}</g><g class="hcells" opacity=".92">{"".join(cells)}</g>')
    river = thames()
    if river:
        pts_ = " ".join("{:.1f},{:.1f}".format(*P(*_merc(la, lo))) for lo, la in river)
        out.append(f'<polyline fill="none" stroke="#9fd0ff" stroke-opacity=".45" stroke-width="3" stroke-dasharray="1 7" stroke-linecap="round" stroke-linejoin="round" points="{pts_}"/>')
    for m in AREAS:
        cx, cy = P(*_merc(m[3], m[4]))
        dx, dy, anc = NUDGE.get(m[0], (13, 5, "start"))
        if m[0] in by:
            a = by[m[0]]
            out.append(f'<a href="/london/{m[5]}/" class="mk"><title>{e(m[1])}: {a["s"]}/100</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="#fff" stroke="#060f22" stroke-width="3"/>'
                       f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" font-size="15" font-weight="700" fill="#fff" paint-order="stroke" stroke="#060f22" stroke-width="4" stroke-linejoin="round">'
                       f'{e(m[0])} <tspan fill="#9fe8d2">{a["s"]}</tspan></text></a>')
        else:
            out.append(f'<a href="/london/{m[5]}/" class="mk lk"><title>{e(m[1])}: score included with Pro</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="#060f22" stroke="#c8d4e8" stroke-width="2" stroke-dasharray="3 2"/>'
                       f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" font-size="13" fill="#c8d4e8" paint-order="stroke" stroke="#060f22" stroke-width="4" stroke-linejoin="round">{e(m[0])}</text></a>')
    out.append("</svg>")
    return "".join(out)


def heat_summary():
    tiles = tile_data()
    if not tiles:
        return ""
    bands = [("Changing fast", 80, 101, hcol(84)), ("Changing", 65, 80, hcol(71)), ("Steady", 50, 65, hcol(58)), ("Quiet", 0, 50, hcol(38))]
    n = len(tiles)
    counts = [(b, sum(1 for v in tiles.values() if b[1] <= v.get("s", 0) < b[2])) for b in bands]
    bar = "".join(f'<i style="width:{c / n * 100:.1f}%;background:{b[3]}" title="{e(b[0])}: {c}"></i>' for b, c in counts if c)
    keys = "".join(f'<span><u style="background:{b[3]}"></u><b>{c}</b> {e(b[0].lower())} ({round(c / n * 100)}%)</span>' for b, c in counts if c)
    return (f'<div class="hsum"><div class="hleg"><span>Quiet</span><i></i><span>Changing fast</span></div>'
            f'<div class="hbar">{bar}</div><div class="hkeys">{keys}</div>'
            f'<p class="small muted" style="margin:10px 0 0">Of the {n} map squares scored across London this week. Each square is about 3 km across and scored on the same seven signals.</p></div>')


HEAT_JS = """<script>(function(){var m=document.querySelector(".ixmap");if(!m)return;var tip=document.createElement("div");tip.className="htip";m.appendChild(tip);
m.addEventListener("mousemove",function(ev){var t=ev.target.closest&&ev.target.closest(".hc");if(!t){tip.style.opacity=0;return}
var r=m.getBoundingClientRect();tip.textContent=t.getAttribute("data-t");tip.style.left=Math.min(r.width-230,ev.clientX-r.left+14)+"px";tip.style.top=(ev.clientY-r.top+14)+"px";tip.style.opacity=1});
m.addEventListener("mouseleave",function(){tip.style.opacity=0})})();</script>"""


def monthyear(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%B %Y")
    except ValueError:
        return iso


def _num(s):
    try:
        return int(str(s).replace(",", ""))
    except ValueError:
        return 0


def _bars(items, key, lab):
    mx = max([abs(x.get(key) or 0) for x in items] + [0.0001])
    return "".join(f'<div class="btb"><span>{e(lab(x))}</span><i><u style="width:{max(3, abs(x.get(key) or 0) / mx * 100):.0f}%"></u></i>'
                   f'<b>{pct(x.get(key))}</b></div>' for x in items)


def backtest_html():
    try:
        bt = json.loads((ROOT / "data" / "backtest.json").read_text())
    except (OSError, ValueError):
        return ""
    pop = bt.get("population_test") or {}
    hdt = (bt.get("headroom_tests") or [{}])[0]
    cards = ""
    if pop.get("bands"):
        hi = next((b for b in pop["bands"] if b["band"].startswith("80")), None)
        lo = next((b for b in pop["bands"] if b["band"].startswith("0")), None)
        beat = (f'<p class="small muted" style="margin-top:12px">{round(hi["beat_london"] * 100)}% of areas scoring 80+ grew faster than London as a whole '
                f'({pct(pop.get("london_growth"))}), against {round(lo["beat_london"] * 100)}% of areas scoring under 40.</p>') if hi and lo else ""
        cards += ('<div class="apc"><div class="eyebrow">Test 1 · Population</div><h3 class="bth">High scores were followed by more residents.</h3>'
                  f'<p class="small muted">We rebuilt the planning part of the Index as it stood in {e(monthyear(pop.get("start", "")))} for {pop.get("areas")} areas of London, '
                  f'then measured each area’s population change ({e(pop.get("years", ""))}, ONS). Median growth per area:</p>'
                  + _bars(pop["bands"], "median_growth", lambda x: "Score " + x["band"].replace("0–39", "under 40")) + beat + "</div>")
    if hdt.get("thirds"):
        cards += ('<div class="apc"><div class="eyebrow">Test 2 · Prices</div><h3 class="bth">On its own, momentum didn’t predict prices. Cheaper areas did better.</h3>'
                  f'<p class="small muted">Resale prices, like-for-like by property type, from the year to {e(monthyear(hdt.get("start", "")))} to the year to {e(monthyear(hdt.get("end", "")))} '
                  f'(HM Land Registry, {hdt.get("areas")} areas):</p>'
                  + _bars(hdt["thirds"], "median_growth", lambda x: x["group"].capitalize() + " third")
                  + '<p class="small muted" style="margin-top:12px">High planning activity was not followed by faster price growth: lots of new homes can hold resale '
                    'prices back. That’s why every area also shows <b style="color:#fff">price headroom</b>. Use the score to find where demand is growing, and headroom '
                    'to judge value.</p></div>')
    if not cards:
        return ""
    return ('<section class="ap-s"><div class="wrap"><div class="eyebrow">Does it work?</div><h2>We tested it on the past.</h2>'
            '<p class="ap-sub">We rebuilt the planning half of the Index as it stood years ago and checked what happened next. Only the planning signals can be '
            'rebuilt historically, and past patterns don’t guarantee future ones.</p>'
            f'<div class="apg2">{cards}</div><p class="small muted" style="margin-top:14px"><a href="/methodology.html" style="color:var(--accent)">'
            'Full back-test results and method</a>.</p></div></section>')


SIG_NAME = {"act": "planning activity", "pipe": "housing pipeline", "ma": "office-to-home conversions", "com": "commercial floorspace",
            "transport": "station use", "population": "population", "prices": "house prices"}


def _list(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def _ptsw(v):
    v = abs(v or 0)
    return f"{v} point" + ("" if v == 1 else "s")


def week_summary(pub):
    """A short plain-English summary of the week, built only from this week's public top 10."""
    top = sorted(pub["areas"], key=lambda a: -a["s"])
    if not top:
        return ""
    keys = pub.get("keys", [])
    def drivers(a, k):
        return [SIG_NAME[s] for s, t in zip(keys, a.get("tr") or []) if t == k and s in SIG_NAME]
    lead = top[0]
    c = lead.get("c") or 0
    s1 = f"{lead['f']} leads the Index at {lead['s']}/100" + (f", {'up' if c > 0 else 'down'} {_ptsw(c)} this month" if c else ", unchanged this month")
    up = drivers(lead, "u")
    s1 += (f"; over the past year its {_list(up[:3])} {'have' if len(up) > 1 else 'has'} been rising." if up else ".")
    movers = [a for a in top if a is not lead and a.get("c12")]
    out = [s1]
    if movers:
        r = max(movers, key=lambda a: a["c12"])
        f = min(movers, key=lambda a: a["c12"])
        if r["c12"] > 0:
            ru = drivers(r, "u")
            out.append(f"{r['f']} has gained the most over 12 months, up {_ptsw(r['c12'])} to {r['s']}" + (f", with rising {_list(ru[:2])}." if ru else "."))
        if f["c12"] < 0 and f is not r:
            fd = drivers(f, "d")
            out.append(f"{f['f']} has lost the most, down {_ptsw(f['c12'])} to {f['s']}" + (f", as {_list(fd[:2])} {'have' if len(fd[:2]) > 1 else 'has'} fallen." if fd else "."))
    n_fast = sum(1 for a in top if a["s"] >= 80)
    n_ch = sum(1 for a in top if 65 <= a["s"] < 80)
    out.append(f"Of this week’s top 10, {n_fast} {'is' if n_fast == 1 else 'are'} changing fast and {n_ch} changing.")
    return " ".join(out)


def _leader_value(k, a):
    raw, off = a.get("raw") or {}, a.get("off") or {}
    if k == "act":
        return f"{nf(raw.get('act'))} significant applications"
    if k == "pipe":
        return f"{homes(a)} net new homes proposed"
    if k == "ma":
        n = max(0, round((raw.get("ma") or 0) - 0.5 * (raw.get("ma_n") or 0)))
        return f"{nf(n)} homes via office-to-home" if n else "office-to-home conversions"
    if k == "com":
        return f"{nf(raw.get('com'))} m² of commercial space"
    if k == "transport" and off.get("transport") is not None:
        return f"station use {pct(off['transport'])} ({e(off.get('transport_span', ''))})"
    if k == "population" and off.get("population") is not None:
        return f"population {pct(off['population'])} ({e(off.get('population_span', ''))})"
    if k == "prices" and off.get("prices") is not None:
        return f"resale prices {pct(off['prices'])} on a year earlier"
    return ""


def signal_leaders(pub):
    top = pub["areas"]
    keys, labels = pub.get("keys", []), pub.get("labels", [])
    cards = []
    for i, k in enumerate(keys):
        have = [a for a in top if len(a.get("x") or []) > i and a["x"][i] is not None]
        if not have:
            continue
        a = max(have, key=lambda a: a["x"][i])
        cards.append(f'<a class="apc ldr" href="/london/{SLUG.get(a["n"], "")}/"><span class="eyebrow">{e(SIGNAL_INFO.get(k, (labels[i] if i < len(labels) else k,))[0])}</span>'
                     f'<b>{e(a["f"])}</b><span>{_leader_value(k, a)}</span><em>{a["x"][i]}/100 on this signal</em></a>')
    return ('<section class="ap-s"><div class="wrap"><div class="eyebrow">Signal leaders</div><h2>What’s driving the top 10.</h2>'
            '<p class="ap-sub">For each of the seven signals, the top-10 neighbourhood that scores highest on it this week. A score on a signal is a ranking: 95 means more than about 95% of London.</p>'
            f'<div class="ldrs">{"".join(cards)}</div></div></section>') if cards else ""


def update_history(pub):
    """Keep a weekly record of the public top 10 (data/history.json), for the trend lines.
    The first run also records each area's score 30 days and 12 months earlier, which the Index already works out."""
    f = ROOT / "data" / "history.json"
    try:
        h = json.loads(f.read_text())
    except (OSError, ValueError):
        h = {"note": "Weekly Momentum scores for each week's public top 10. Points marked derived come from the Index's own 30-day and 12-month changes.", "weeks": []}
    weeks = h.setdefault("weeks", [])
    g = dt.date.fromisoformat(pub["generated"])
    if not weeks:
        for days, key in ((365, "c12"), (30, "c")):
            pts_ = {a["n"]: a["s"] - a[key] for a in pub["areas"] if a.get(key) is not None}
            if pts_:
                weeks.append({"d": (g - dt.timedelta(days=days)).isoformat(), "a": pts_, "derived": True})
    now = {a["n"]: a["s"] for a in pub["areas"]}
    weeks[:] = [w for w in weeks if w["d"] != pub["generated"]] + [{"d": pub["generated"], "a": now}]
    weeks.sort(key=lambda w: w["d"])
    del weeks[:-110]
    f.write_text(json.dumps(h, ensure_ascii=False, indent=1))
    return h


def sparkline(h, n, w=120, ht=30):
    pts_ = [(dt.date.fromisoformat(x["d"]), x["a"][n]) for x in h.get("weeks", []) if n in x.get("a", {})]
    if len(pts_) < 2:
        return ""
    d0, d1 = pts_[0][0], pts_[-1][0]
    span = max(1, (d1 - d0).days)
    lo, hi = min(v for _, v in pts_), max(v for _, v in pts_)
    lo, hi = lo - 2, hi + 2
    P = [(3 + (d - d0).days / span * (w - 6), ht - 3 - (v - lo) / (hi - lo) * (ht - 6)) for d, v in pts_]
    col = "#7ee0b5" if pts_[-1][1] > pts_[0][1] else "#ffb38a" if pts_[-1][1] < pts_[0][1] else "#9aa3b5"
    first = pts_[0]
    return (f'<svg class="spk" viewBox="0 0 {w} {ht}" width="{w}" height="{ht}" aria-label="Score from {first[1]} on {e(day(first[0].isoformat()))} to {pts_[-1][1]}">'
            f'<title>{e(day(first[0].isoformat()))}: {first[1]} → now: {pts_[-1][1]}</title>'
            f'<polyline fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in P)}"/>'
            f'<circle cx="{P[-1][0]:.1f}" cy="{P[-1][1]:.1f}" r="2.6" fill="{col}"/></svg>')


def cite_box(pub):
    wk = day(pub["generated"])
    txt = f"Source: Terrayne London Momentum Index, {wk} (terrayne.co/london)"
    return (f'<div class="apc cite"><div><div class="eyebrow">Quoting the Index?</div><p style="margin:6px 0 0;color:#c8d4e8">You’re welcome to quote individual scores and findings, '
            f'with credit and a link. Use this line:</p><code id="citetxt">{e(txt)}</code></div>'
            f'<button class="btn ghost sm" type="button" id="citebtn">Copy</button></div>'
            '<script>(function(){var b=document.getElementById("citebtn");if(!b)return;b.onclick=function(){var t=document.getElementById("citetxt").textContent;'
            '(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent="Copied"},function(){var r=document.createRange();'
            'r.selectNodeContents(document.getElementById("citetxt"));var s=getSelection();s.removeAllRanges();s.addRange(r)});setTimeout(function(){b.textContent="Copy"},2000)}})();</script>')


def london_page(pub, hist=None):
    by = {a["n"]: a for a in pub["areas"]}
    top = sorted(pub["areas"], key=lambda a: -a["s"])
    upd = day(pub["generated"])
    W, keys = pub.get("weights", {}), pub.get("keys", [])
    B = pub.get("bench") or {}
    tracked = pub["tracked"]
    tiles = pub.get("tiles") or 0
    radius = f"{pub.get('radius_km', 1.72):.1f}"
    sgn = lambda v: "0" if not v else (f"+{v}" if v > 0 else f"−{abs(v)}")
    cls = lambda v: "up" if (v or 0) > 0 else "down" if (v or 0) < 0 else ""

    rows = []
    for i, a in enumerate(top, 1):
        v = verdict(a["s"])
        c = VCOL[v]
        cf = (a.get("cf") or ["M"])[0]
        rows.append(f'<tr><td class="n rk">{i}</td><td><a class="nm" href="/london/{SLUG.get(a["n"], "")}/"><b><span class="rkm">{i}. </span>{e(a["f"])}</b></a><span class="muted small">{e(a["b"])}</span></td>'
                    f'<td data-l="Score"><span class="scb"><b>{a["s"]}</b><i><u style="width:{a["s"]}%;background:{c}"></u></i></span></td>'
                    f'<td data-l="Verdict"><span style="color:{c}">{e(v)}</span></td>'
                    f'<td class="n {cls(a.get("c"))}" data-l="30 days">{sgn(a.get("c"))}</td><td class="n {cls(a.get("c12"))}" data-l="12 months">{sgn(a.get("c12"))}</td>'
                    f'<td class="n" data-l="Homes proposed">{e(a.get("u", "—"))}</td><td class="n" data-l="Price headroom">{a.get("hd", "—")}</td>'
                    f'<td data-l="Confidence">{CONF.get(cf, "Medium")}</td><td class="tr" data-l="Trend">{sparkline(hist or {}, a["n"])}</td></tr>')
    board = ('<div class="apw"><table class="ap-t stack lb"><thead><tr><th class="n">#</th><th>Neighbourhood</th><th>Score</th><th>Verdict</th>'
             '<th class="n">30 days</th><th class="n">12 months</th><th class="n">Homes proposed</th><th class="n">Price headroom</th><th>Confidence</th><th>Trend</th></tr></thead><tbody>'
             + "".join(rows) + "</tbody></table></div>")

    up = max(top, key=lambda a: a.get("c") if a.get("c") is not None else -999)
    dn = min(top, key=lambda a: a.get("c") if a.get("c") is not None else 999)
    most = max(top, key=lambda a: _num(a.get("u")))
    head = max(top, key=lambda a: a.get("hd") or 0)
    ptw = lambda v: f"{sgn(v)} pt" + ("" if abs(v or 0) == 1 else "s")
    movers = [("Biggest rise this month", up, f"{ptw(up.get('c'))}, now {up['s']}/100"),
              ("Biggest fall this month", dn, f"{ptw(dn.get('c'))}, now {dn['s']}/100"),
              ("Most new homes proposed", most, f"{e(most.get('u'))} net new homes in 12 months"),
              ("Most price headroom", head, "cheaper than almost all of London" if (head.get("hd") or 0) >= 99 else f"cheaper than {head.get('hd')}% of London")]
    mv = "".join(f'<a class="apc mvr" href="/london/{SLUG.get(a["n"], "")}/"><span class="eyebrow">{e(t)}</span><b>{e(a["f"])}</b><span>{x}</span></a>'
                 for t, a, x in movers)

    locked = "".join(f'<a href="/london/{m[5]}/"><b>{e(m[1])}</b><span>{e(m[2])} · score, signals and trend in Pro</span></a>'
                     for m in sorted(AREAS, key=lambda m: m[1]) if m[0] not in by)

    def sig_rows(ks):
        return "".join(f'<div class="sgx"><div><b>{e(SIGNAL_INFO[k][0])}</b><span>{e(SIGNAL_INFO[k][1])}</span></div><em>{round(W.get(k, 0) * 100)}%</em></div>'
                       for k in ks if k in SIGNAL_INFO)
    plan_k = [k for k in keys if k in ("act", "pipe", "ma", "com")]
    off_k = [k for k in keys if k in ("transport", "population", "prices")]
    pw = round(sum(W.get(k, 0) for k in plan_k) * 100)
    ow = round(sum(W.get(k, 0) for k in off_k) * 100)

    bench = []
    if "act" in B:
        bench.append((nf(B["act"]), "significant planning applications in 12 months"))
    if "pipe" in B:
        bench.append((nf(B["pipe"]), "net new homes proposed"))
    if "com" in B:
        bench.append((f"{nf(B['com'])} m²", "net new commercial floorspace proposed"))
    if "transport" in B:
        bench.append((pct(B["transport"]), "change in station use"))
    if "population" in B:
        bench.append((pct(B["population"]), "population change"))
    if "price_level" in B:
        bench.append((f"£{nf(B['price_level'])}", "median sale price" + (f", {pct(B['prices'])} on a year earlier" if "prices" in B else "")))
    bn = "".join(f'<div class="apc"><b>{v}</b><span>{l}</span></div>' for v, l in bench)

    qs = [("What is the London Momentum Index?",
           f"A score from 0 to 100 for how fast a London neighbourhood is changing, compared with the rest of London. It combines seven signals from five official sources: "
           f"planning applications, new homes and commercial space proposed, office-to-home conversions, station use, population and resale prices. Terrayne tracks "
           f"{tracked} neighbourhoods in detail and scores every part of London on a grid of map squares about 3 km across."),
          ("How is the score calculated?",
           f"For each signal, an area is ranked against every same-sized area of London, so a 90 means more activity than about 90% of London. The seven rankings are "
           f"combined with fixed weights: planning signals {pw}%, official statistics {ow}%. Where a signal has no data, the others are re-weighted, and the data "
           f"confidence rating says so. The full method is on the <a href=\"/methodology.html\">methodology page</a>."),
          ("Does a high score mean prices will rise?",
           "No. The score measures activity, not future prices. Our back-test found high scores were followed by faster population growth, but not by faster price "
           "growth: cheaper areas did better. Use the score to see where change and demand are building, and price headroom to judge value. It isn’t investment advice."),
          ("How often is it updated?",
           "Every Monday by 7am UK time, from new planning filings in the GLA Planning London Datahub. Station use, population and sale prices update when the "
           "government publishes them, from monthly to yearly."),
          (f"Why these {tracked} neighbourhoods?",
           f"They are London’s main regeneration and growth areas, from Stratford and Old Kent Road to Wembley Park and Croydon. Each is measured within about "
           f"{radius} km of its centre. Any other London postcode can still be checked: the postcode check scores the area it sits in."),
          ("Can I see the score for my own postcode?",
           "Yes. The postcode check on the homepage shows the score for the area around any London postcode, with every significant scheme within walking distance. "
           "It’s free 3 times a month, and unlimited with Pro."),
          ("What does data confidence mean?",
           "How complete the evidence behind a score is. An area with no stations has no station-use signal, and one with few sales has thin price data. High means "
           "no gaps, Medium one or two, Low three or more. It isn’t a forecast."),
          ("What’s free and what’s in Pro?",
           f"This week’s top 10 is free, with every neighbourhood page and 3 postcode checks a month. Pro (£29 a month) adds all {tracked} neighbourhoods with history "
           f"and 12-month trends, unlimited postcode checks and comparisons, a watchlist and the Monday Brief. Team (£99 a month) is for up to 5 people and adds "
           f"same-day alerts near your saved places.")]

    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › Momentum Index</div>
<div class="eyebrow">The Development Momentum Index · London · Updated {e(upd)}</div>
<h1>Where London is changing, scored every week.</h1>
<p class="ap-lead">The Momentum Index gives London neighbourhoods a score from 0 to 100 for how fast they are changing, from seven signals across five official sources: what’s being planned, and what’s already happening on the ground. Here’s this week’s top 10, free.</p>
<div class="kn k4"><div class="apc"><b>{tracked}</b><span>regeneration neighbourhoods tracked in detail</span></div><div class="apc"><b>{nf(tiles) if tiles else "All"}</b><span>map squares scored across London</span></div><div class="apc"><b>7</b><span>signals from 5 official sources</span></div><div class="apc"><b>Mon 7am</b><span>new scores every week</span></div></div>
<div class="apc wk"><div class="eyebrow">This week in brief · {e(upd)}</div><p>{e(week_summary(pub))}</p></div>
<div class="ap-cta"><a class="btn" href="/#check">Score any London postcode</a><a class="btn ghost" href="/#index">Open the interactive map</a></div>
</div></section>

<section class="ap-s" style="padding-top:18px"><div class="wrap">
<h2>This week’s top 10</h2><p class="ap-sub">Click a neighbourhood for its signals, numbers and largest schemes. Changes are in points. Homes proposed are net, from the last 12 months. Price headroom 80 means cheaper than 80% of London. Trend lines run from a year ago to now, and fill in week by week.</p>
{board}
<div class="kn k4 mvs" style="margin-top:18px">{mv}</div>
</div></section>

{signal_leaders(pub)}

<section class="ap-s"><div class="wrap">
<div class="eyebrow">The heat map</div><h2>All of London, square by square.</h2><p class="ap-sub">Every part of London scored on the same seven signals, in squares about 3 km across. Brighter means changing faster. White dots are this week’s top 10; dashed dots are also tracked, with scores in Pro. Hover a square for its score, or tap a neighbourhood for its page.</p>
<div class="apc ixmap">{london_map(pub)}</div>
{heat_summary()}
<p class="small muted" style="margin:12px 0 0">Want the score for a specific street? <a href="/#check" style="color:var(--accent)">Check any London postcode</a> for its square’s score and every significant scheme within walking distance.</p>
{HEAT_JS}
<h2 style="margin-top:44px">Also tracked</h2><p class="ap-sub">These neighbourhoods are outside this week’s top 10. Their scores, the signals behind them and their trends are included with Pro, and each page shows new planning filings nearby.</p>
<div class="alist">{locked}</div>
<div class="ap-cta"><a class="btn" href="/account.html?signup&amp;plan=pro">See every score with Pro</a></div>
</div></section>

<section class="ap-s"><div class="wrap">
<div class="eyebrow">How it works</div><h2>Seven signals. One score.</h2>
<p class="ap-sub">Each signal ranks an area against every same-sized area of London, so a 90 means more activity than about 90% of the city. Planning filings show what’s coming; official statistics show what’s already changing. <a href="/methodology.html" style="color:var(--accent)">Read the full method</a>.</p>
<div class="apg2">
<div class="apc"><div class="sgh">What’s coming <span>planning filings, last 12 months · {pw}% of the score</span></div>{sig_rows(plan_k)}<p class="small muted" style="margin:12px 0 0">Source: GLA Planning London Datahub. Applications aren’t approvals, so the signals count live schemes only.</p></div>
<div class="apc"><div class="sgh">What’s already changing <span>official statistics · {ow}% of the score</span></div>{sig_rows(off_k)}<p class="small muted" style="margin:12px 0 0">Sources: TfL and the Office of Rail and Road, ONS, HM Land Registry.</p></div>
</div>
</div></section>

<section class="ap-s"><div class="wrap">
<h2>Reading a score</h2><p class="ap-sub">Every area gets a score, a verdict, a direction of travel and a data confidence rating.</p>
<div class="apg3">
<div class="apc"><div class="eyebrow">Verdict</div><ul class="vlist"><li><i style="background:#4f9be8"></i><b>80–100</b> Changing fast</li><li><i style="background:#5fd6b8"></i><b>65–79</b> Changing</li><li><i style="background:#9aa3b5"></i><b>50–64</b> Steady</li><li><i style="background:#52617f"></i><b>Under 50</b> Quiet</li></ul></div>
<div class="apc"><div class="eyebrow">Direction of travel</div><p class="small muted" style="margin:8px 0 0">Each signal is marked <span style="color:#7ee0b5">↑ rising</span>, → stable or <span style="color:#ffb38a">↓ falling</span> over 12 months, and every score shows its change over 30 days and 12 months, so you can tell an area that’s speeding up from one that has peaked.</p></div>
<div class="apc"><div class="eyebrow">Data confidence</div><p class="small muted" style="margin:8px 0 0">High, Medium or Low, depending on gaps in the evidence: no nearby stations, or too few applications, sales or census areas. A Low score rests on less evidence, so check it more carefully. <a href="/methodology.html#confidence" style="color:var(--accent)">How it’s rated</a>.</p></div>
<div class="apc"><div class="eyebrow">Price headroom</div><p class="small muted" style="margin:8px 0 0">Not part of the score: how local prices compare with the rest of London. 80 means cheaper than 80% of London. Pair it with momentum to find areas that are changing but where prices are still comparatively low.</p></div>
</div>
</div></section>

<section class="ap-s"><div class="wrap">
<h2>A typical London area, for comparison</h2><p class="ap-sub">The median for every same-sized area of London over the same 12 months. Every neighbourhood page shows its own figures against these.</p>
<div class="kn">{bn}</div>
</div></section>

{backtest_html()}

<section class="ap-s"><div class="wrap">
<h2>Who uses it</h2>
<div class="apg3">
<div class="apc"><div class="eyebrow">Developers</div><p class="small muted" style="margin:8px 0 0">Shortlist areas where planning, transport and population are all moving, then check the schemes and decisions behind the score before you spend time on a site.</p></div>
<div class="apc"><div class="eyebrow">Planning consultants</div><p class="small muted" style="margin:8px 0 0">Evidence for clients on how an area is changing, with council references for every scheme, plus <a href="/class-ma/" style="color:var(--accent)">office-to-home approval rates</a> by borough.</p></div>
<div class="apc"><div class="eyebrow">Agents and investors</div><p class="small muted" style="margin:8px 0 0">Context for valuations and listings: what’s planned within walking distance, how the area compares with London, and how much price headroom is left.</p></div>
</div>
</div></section>

<section class="ap-s"><div class="wrap">
<div class="apc ix-plans"><div><div class="eyebrow">Follow the Index</div><h2 style="margin:6px 0 8px">Every score, every week, in your inbox.</h2>
<p class="muted" style="margin:0;max-width:620px">Pro (£29 a month) unlocks all {tracked} neighbourhoods with history and trends, unlimited postcode checks and comparisons, and a watchlist with the Monday Brief: what moved, what was filed and what was decided, by 7am UK time. Team (£99 a month) adds same-day alerts for up to 5 people.</p></div>
<div class="ap-cta" style="margin-top:0"><a class="btn" href="/account.html?signup&amp;plan=pro">Get Pro</a><a class="btn ghost" href="/#pricing">Compare plans</a></div></div>
<div style="margin-top:22px">{brief_box("", "See a real Monday Brief first.", "Pick a neighbourhood and we’ll email you this week’s brief. No account or card needed.")}</div>
</div></section>

<section class="ap-s"><div class="wrap">
<h2>Questions about the Index</h2>{faq_html(qs)}
<div style="margin-top:28px">{cite_box(pub)}</div>
<h2 style="margin-top:44px">Every tracked neighbourhood</h2>
{other_links("")}
<p class="small muted" style="margin-top:26px">Sources: GLA Planning London Datahub, TfL, Office of Rail and Road, ONS and HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0. Powered by TfL Open Data. Contains OS, Royal Mail, National Statistics and HM Land Registry data © copyright and database right 2026 (<a href="/methodology.html#sources" style="color:inherit;text-decoration:underline">full data credits</a>). Scores describe activity, not future prices, and aren’t investment advice.</p>
</div></section>"""
    ld = [faq_ld(qs), {"@context": "https://schema.org", "@type": "Dataset", "name": "London Development Momentum Index",
                       "description": f"Weekly 0–100 scores for how fast London neighbourhoods are changing, from planning filings, station use, population and resale prices. Top {len(top)} published free.",
                       "url": SITE + "/london/", "creator": {"@type": "Organization", "name": "Terrayne", "url": SITE},
                       "dateModified": pub["generated"], "spatialCoverage": "Greater London", "isAccessibleForFree": True}]
    return page("London Momentum Index: which neighbourhoods are changing fastest | Terrayne",
                f"This week’s London Momentum Index: {tracked} regeneration neighbourhoods scored 0–100 from planning filings, station use, population and sale prices. Top 10 free, updated every Monday.",
                "/london/", body, ld)


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
            ("Hear about new filings first", "Save the sites and patches you work on. Every new Class MA application within a 5, 10 or 20-minute walk lands in your Monday Brief by 7am, and Team plans get an email the same day."),
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
           "The borough table and the latest filings are free, with no account. Pro (£29 a month) adds the Monday Brief, including new filings near the sites you save, the full "
           "planning signal feed with “why it matters”, unlimited postcode checks and PDF reports. Team (£99 a month) covers up to 5 people and adds same-day email alerts when a big scheme near your saved places is filed, approved or refused.")]
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
{brief_box(title="See a real Monday Brief first.", sub="Pick a neighbourhood and we’ll email you this week’s brief, including new office-to-home filings nearby. No account or card needed.")}
</div></section>
<section class="ap-s"><div class="wrap">
<div class="apc" style="text-align:center;padding:clamp(26px,4vw,44px)">
<h2 style="font-size:clamp(26px,3.6vw,38px)">Get new Class MA filings near your sites, every Monday.</h2>
<p class="ap-sub" style="margin:0 auto 6px">Pro is £29 a month, or £290 a year. Cancel any time. Team is £99 a month for up to 5 people.</p>
<p class="ap-sub" style="margin:0 auto 6px">Work at a planning consultancy or developer? We’re taking on a small number of London firms as founding partners, with a guided setup and a say in what we build next.</p>
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
    hist = update_history(pub)
    (ROOT / "london" / "index.html").write_text(london_page(pub, hist))
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
