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
.stp{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.stp .apc em{display:block;font-style:normal;font-family:ui-monospace,Menlo,monospace;color:#9fd0ff;font-size:12px;margin-bottom:8px}
.stp .apc b{display:block;font-size:16.5px;margin-bottom:6px}.stp .apc p{margin:0;color:var(--mute);font-size:14px;line-height:1.55}.stp .apc a{color:var(--accent)}
.bpg .stp{grid-template-columns:1fr 1fr}.bpg .stp .apc:last-child:nth-child(odd){grid-column:1/-1}
.wx{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wx .apc:nth-child(3){grid-column:1/-1}.wx em{display:block;font-style:normal;font-family:ui-monospace,Menlo,monospace;color:#9fd0ff;font-size:12px;margin-bottom:8px}
.wx p{margin:0 0 10px;color:#c8d4e8;line-height:1.6;font-size:14.5px}.wx ul{margin:0 0 10px;padding-left:18px;color:#c8d4e8;font-size:14px;line-height:1.55}.wx ul a{color:var(--accent)}.wx .apc>a{color:var(--accent);font-size:13.5px}
.wxt tr.me td{background:rgba(79,155,232,.08)}
.wxend{display:flex;justify-content:space-between;align-items:center;gap:22px;flex-wrap:wrap;margin-top:14px;background:linear-gradient(135deg,rgba(30,64,120,.45),rgba(13,24,48,.8));border-color:#2f4677}.wxend p{margin:6px 0 0;color:#e3ebf7;line-height:1.6;max-width:680px}.wxt tr.me td:first-child b{color:#9fd0ff}.rpg .stp{grid-template-columns:1fr}.dpg{align-items:start}
.tk{list-style:none;padding:0;margin:10px 0 0}.tk li{position:relative;padding:7px 0 7px 26px;color:#c8d4e8;font-size:14.5px;line-height:1.5;border-bottom:1px solid rgba(28,43,77,.6)}.tk li:last-child{border-bottom:0}
.tk li:before{content:"";position:absolute;left:2px;top:13px;width:12px;height:7px;border-left:2px solid #5fd6b8;border-bottom:2px solid #5fd6b8;transform:rotate(-45deg)}
.mail{background:#0a1529;border:1px solid #1c2b4d;border-radius:20px;padding:18px;font-size:14px;color:#c8d4e8}.mail .mh{display:flex;justify-content:space-between;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--mute);border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:12px}
.mail .me{letter-spacing:.18em;text-transform:uppercase;font-size:11px;color:#9fd0ff;margin:0}.mail h3{margin:6px 0 8px;font-size:20px;color:#fff}.mail .hl2{margin:0 0 12px;line-height:1.55}
.mail .mc{background:#0d1830;border:1px solid #1c2b4d;border-radius:14px;padding:14px 16px;margin:0 0 10px}.mail .ma{font-size:12px;color:var(--mute)}.mail h4{margin:4px 0 6px;font-size:15.5px;color:#fff}
.mail p{margin:6px 0;line-height:1.55}.mail .dim{color:var(--mute);font-size:13px}.mail ul{margin:6px 0 0;padding-left:18px}.mail li{margin:0 0 10px;line-height:1.5}.mail li span{color:var(--mute)}.mail a{color:#4c9bff}
.mail .mt{font-weight:700;color:#fff;margin:14px 0 8px}.mail .foot{font-size:11.5px;color:#52617f;margin:10px 0 0}
.wk{margin:16px 0 4px;border-color:#2f4677;background:linear-gradient(135deg,rgba(30,64,120,.35),rgba(13,24,48,.75))}.wk p{margin:8px 0 0;font-size:clamp(15.5px,1.8vw,17.5px);line-height:1.65;color:#e3ebf7}
.lb td.tr{padding-right:0}.spk{display:block}
.cns{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.cn p{margin:6px 0 10px;color:var(--mute);font-size:13px;line-height:1.45}
.cn ol{list-style:none;margin:0;padding:0}.cn li{display:grid;grid-template-columns:20px minmax(0,1fr) auto;gap:8px;align-items:baseline;padding:8px 0;border-top:1px solid rgba(28,43,77,.7);font-size:14px}
.cn li em{font-style:normal;color:var(--mute);font-family:ui-monospace,Menlo,monospace;font-size:12px}.cn li a{color:#fff}.cn li a:hover{text-decoration:underline}.cn li b{color:#9fe8d2;font-variant-numeric:tabular-nums;font-size:13px;text-align:right;white-space:nowrap}.cn li.none{display:block;color:var(--mute)}
@media(max-width:1000px){.cns{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.cns{grid-template-columns:1fr}}
.ldrs{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}.ldr{display:block;transition:border-color .2s}.ldr:hover{border-color:#3a5a92}
.ldr .eyebrow{display:block;font-size:11px;margin-bottom:8px}.ldr b{display:block;font-size:18px}.ldr span{display:block;color:#c8d4e8;font-size:14px;margin-top:4px}.ldr em{display:block;font-style:normal;color:var(--mute);font-size:12.5px;margin-top:8px}
.cite{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.cite code{display:block;margin-top:10px;font-size:13px;color:#9fd0ff;background:#081227;border:1px solid var(--line);border-radius:10px;padding:9px 12px;white-space:normal}
.ixh{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;padding:10px 12px 14px}.ixh small{color:var(--mute);letter-spacing:.14em;text-transform:uppercase;font-size:11px}.ixh h3{margin:4px 0 0;font-size:18px}
.leg{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:12px;color:var(--mute);align-items:center}.leg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.lg-grad{display:inline-flex;align-items:center;gap:8px}.lg-grad b{display:inline-block;width:110px;height:8px;border-radius:9px;background:linear-gradient(90deg,rgb(16,28,56),rgb(30,62,120) 38%,rgb(44,102,186) 58%,rgb(66,150,230) 72%,rgb(95,214,184) 85%,rgb(200,250,232))}.lg-grad em{font-style:normal}
.ixwrap{position:relative;border-radius:14px;overflow:hidden}.maphint{font-size:13px;color:var(--mute);margin:12px 12px 4px}
.hm rect.ht{cursor:pointer;transition:stroke .15s}.hm rect.ht:hover,.hm rect.ht.on{stroke:#fff;stroke-width:2.5}.hm .mk{cursor:pointer}.hm .mk:hover text{text-decoration:underline}
#ixtip{position:absolute;z-index:5;min-width:190px;max-width:240px;background:rgba(10,20,38,.97);border:1px solid rgba(159,208,255,.25);border-radius:14px;padding:12px 14px;box-shadow:0 18px 40px -14px rgba(0,0,0,.8);font-size:13px}
#ixtip .tt-h{font-weight:600;color:#fff;display:flex;align-items:center;gap:8px}#ixtip .tt-h i{width:9px;height:9px;border-radius:50%}
#ixtip .tt-p{color:var(--mute);margin:3px 0 8px}#ixtip .tt-s{color:#c8d4e8;margin-bottom:10px}#ixtip .tt-s a{color:#9fd0ff;text-decoration:underline}
#ixtip .tt-b{width:100%;background:#fff;color:#0a1223;border:0;border-radius:99px;padding:8px 10px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer}
.hsum{margin-top:16px}.hbar{display:flex;height:12px;border-radius:9px;overflow:hidden;margin:0 0 10px;gap:2px}.hbar i{display:block;height:100%}
.hkeys{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13.5px;color:#c8d4e8}.hkeys u{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
@media(max-width:820px){.apg,.apg2,.bpg .stp,.wx{grid-template-columns:1fr}.kn,.kn.k4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.ap-t.stack thead{display:none}.ap-t.stack,.ap-t.stack tbody,.ap-t.stack tr,.ap-t.stack td{display:block;width:100%}
 .ap-t.stack tr{padding:12px 0;border-bottom:1px solid var(--line)}.ap-t.stack td{border:0;padding:2px 0;text-align:left}
 .ap-t.stack td[data-l]{display:inline-block!important;width:auto!important;font-family:inherit;letter-spacing:0;text-transform:none;margin:4px 14px 0 0;font-size:13px}.ap-t.stack td[data-l]:before{content:attr(data-l)": ";color:var(--mute)}
 .sg{grid-template-columns:minmax(0,1fr) 44px 70px;font-size:14px}
 .hm .lk text{display:none}.hm text{font-size:30px}.hm .mk circle{r:11px}
 .lb td.rk{display:none!important}.lb .rkm{display:inline}.lb td[data-l="Score"]{display:block!important;margin:6px 0 2px!important}.lb td[data-l="Score"]:before{content:none!important}.scb{max-width:260px}}
</style>"""

DD2_JS = '''<script>/* second menu dropdown: Tools */(function(){var d=document.getElementById("dd2");if(!d)return;var b=d.querySelector("button"),d1=document.getElementById("dd");
function shut(){d.classList.remove("open");b.setAttribute("aria-expanded",false)}
b.onclick=function(e){e.stopPropagation();var o=d.classList.toggle("open");b.setAttribute("aria-expanded",o);if(d1){d1.classList.remove("open");var b1=d1.querySelector("button");if(b1)b1.setAttribute("aria-expanded",false)}};
document.addEventListener("click",shut);if(d1){var b1=d1.querySelector("button");if(b1)b1.addEventListener("click",shut)}
d.querySelectorAll("a").forEach(function(a){a.addEventListener("click",function(){shut();var n=document.querySelector("nav");if(n)n.classList.remove("open")})})})();</script>'''

DD_JS = """<script>(function(){var dd=document.getElementById("dd");if(!dd)return;var b=dd.querySelector("button");
b.onclick=function(e){e.stopPropagation();var o=dd.classList.toggle("open");b.setAttribute("aria-expanded",o)};
document.addEventListener("click",function(){dd.classList.remove("open");b.setAttribute("aria-expanded",false)})})();</script>"""


def footer():
    links = [("/about.html", "About"), ("/london/", "Momentum Index"), ("/monday-brief/", "Monday Brief"), ("/postcode-report/", "Postcode Report"),
             ("/developers/", "For firms"), ("/class-ma/", "Class MA"), ("/planning.html", "Planning tracker"),
             ("/methodology.html", "Methodology"), ("/terms.html", "Terms"), ("/privacy.html", "Privacy")]
    return ('<footer><div class="wrap"><span>© 2026 Terrayne. Property intelligence.</span><span class="fl">'
            + "".join(f'<a href="{h}">{t}</a>' for h, t in links)
            + '<a class="tmark" href="#" aria-label="Back to top"><svg viewBox="0 0 270 143" aria-hidden="true"><path d="M0 40L270 0V46H0Z" fill="currentColor"/>'
            '<rect x="96" y="45" width="20" height="98" fill="currentColor"/></svg></a></span></div></footer>')


def page(title, desc, path, body, jsonld=None):
    head, nav, nav_js = shell()
    # light up the menu item for the section this page belongs to
    sec = "/" + path.strip("/").split("/")[0] + "/" if path.strip("/") else None
    if sec and f'<a href="{sec}">' in nav:
        nav = nav.replace(f'<a href="{sec}">', f'<a href="{sec}" class="act" aria-current="page">', 1)
    url = SITE + path
    meta = (f"<title>{e(title)}</title>\n<meta name=\"description\" content=\"{e(desc)}\">\n<link rel=\"canonical\" href=\"{url}\">\n"
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Terrayne"><meta property="og:title" content="{e(title)}">'
            f'<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}"><meta property="og:image" content="{SITE}/assets/og.png">'
            f'<meta name="twitter:card" content="summary_large_image">\n')
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n' if jsonld else ""
    head = head.replace('<meta name="viewport"', meta + '<meta name="viewport"', 1)
    return (f"{head}{EXTRA_CSS}\n{ld}</head>\n<body>\n{nav}\n<main>\n{body}\n</main>\n{footer()}\n{nav_js}\n{DD_JS}\n{DD2_JS}\n"
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


VCOL = {"Changing fast": "#4f9be8", "Changing": "#5fd6b8", "Steady": "#9aa3b5", "Quiet": "#6f7f9e"}
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


HSTOPS = [(20, (16, 28, 56)), (45, (30, 62, 120)), (58, (44, 102, 186)), (67, (66, 150, 230)), (75, (95, 214, 184)), (85, (200, 250, 232))]
BANDS = [(80, "Changing fast", "#4f9be8"), (65, "Changing", "#5fd6b8"), (50, "Steady", "#9aa3b5"), (0, "Quiet", "#6f7f9e")]   # same as the homepage band()
REGIONS = [(-0.33, 51.6, "NORTH WEST"), (0.0, 51.6, "NORTH EAST"), (-0.35, 51.43, "RIVER THAMES"), (0.02, 51.39, "SOUTH EAST")]   # same as the homepage map


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


def band_of(s):
    return next(b for b in BANDS if s >= b[0])


def _merc(lat, lon, z=13):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


# Label positions for the crowded centre of the map (dx, dy, anchor), so names don't overlap.
NUDGE = {"Elephant": (0, -15, "middle"), "Hammersmith": (-13, 5, "end"), "Nine Elms": (-14, 18, "end"), "Old Kent Road": (14, 20, "start"),
         "Canada Water": (12, -12, "start"), "Whitechapel": (14, -10, "start"), "King’s Cross": (-14, -10, "end"), "Isle of Dogs": (12, 20, "start"),
         "Greenwich Pen.": (12, -4, "start"), "Woolwich": (12, 16, "start"), "Lewisham": (12, 18, "start")}


def tile_data():
    try:
        return json.loads((ROOT / "data" / "tiles.json").read_text()).get("tiles", {})
    except (OSError, ValueError):
        return {}


def london_map(pub):
    """The homepage heat map, drawn large: every scored square in London (public data/tiles.json), the river, region labels and the
    tracked neighbourhoods. Squares show their band, not their exact score (exact scores are a Pro feature, as on the homepage)."""
    tiles = tile_data()
    by = {a["n"]: a for a in pub["areas"]}
    if not tiles:
        return ""
    ks = [(int(k.split("/")[1]), int(k.split("/")[2]), k, v) for k, v in tiles.items()]
    x0, x1 = min(k[0] for k in ks) - 0.6, max(k[0] for k in ks) + 1.6
    y0, y1 = min(k[1] for k in ks) - 0.6, max(k[1] for k in ks) + 1.6
    S = 1100 / (x1 - x0)
    W, H = 1100, (y1 - y0) * S
    P = lambda x, y: ((x - x0) * S, (y - y0) * S)
    out = [f'<svg class="hm" id="ixmapsvg" viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Heat map of the Momentum Index across London" style="width:100%;height:auto;display:block">',
           '<defs><pattern id="gr" width="38" height="38" patternUnits="userSpaceOnUse"><path d="M38 0H0V38" fill="none" stroke="#16233f" stroke-width="1"/></pattern>'
           '<filter id="hglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="20"/></filter></defs>',
           f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="#060f22"/><rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="url(#gr)" opacity=".7"/>']
    glow, cells = [], []
    for x, y, k, v in ks:
        s = v.get("s", 0)
        px, py = P(x, y)
        glow.append(f'<rect x="{px - S * .15:.1f}" y="{py - S * .15:.1f}" width="{S * 1.3:.1f}" height="{S * 1.3:.1f}" fill="{hcol(s)}"/>')
        b = BANDS.index(band_of(s))
        cells.append(f'<rect class="ht" data-k="{k}" data-b="{b}" x="{px:.1f}" y="{py:.1f}" width="{S - 2.5:.1f}" height="{S - 2.5:.1f}" rx="5" fill="{hcol(s)}" fill-opacity=".85"/>')
    out.append(f'<g filter="url(#hglow)" opacity=".5">{"".join(glow)}</g><g class="heat">{"".join(cells)}</g>')
    river = thames()
    if river:
        out.append('<path d="M' + "L".join("{:.1f} {:.1f}".format(*P(*_merc(la, lo))) for lo, la in river)
                   + f'" fill="none" stroke="#1d3358" stroke-width="{S * .3:.1f}" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>')
    out.append('<g fill="#52617f" font-size="14" letter-spacing="4" font-family="ui-monospace,Menlo,monospace" pointer-events="none">'
               + "".join('<text x="{:.0f}" y="{:.0f}">{}</text>'.format(*P(*_merc(la, lo)), nm) for lo, la, nm in REGIONS) + "</g>")
    for m in AREAS:
        cx, cy = P(*_merc(m[3], m[4]))
        dx, dy, anc = NUDGE.get(m[0], (13, 5, "start"))
        if m[0] in by:
            a = by[m[0]]
            c = band_of(a["s"])[2]
            out.append(f'<a href="/london/{m[5]}/" class="mk"><title>{e(m[1])}: {a["s"]}/100</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="#0a1426" stroke="{c}" stroke-width="3"/>'
                       f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" font-size="15" font-weight="700" fill="#fff" paint-order="stroke" stroke="#060f22" stroke-width="4" stroke-linejoin="round">'
                       f'{e(m[0])} <tspan fill="{c}">{a["s"]}</tspan></text></a>')
        else:
            out.append(f'<a href="/london/{m[5]}/" class="mk lk"><title>{e(m[1])}: score included with Pro</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="#0a1426" stroke="#8c9ab3" stroke-width="2" stroke-dasharray="3 2"/>'
                       f'<text x="{cx + dx:.1f}" y="{cy + dy:.1f}" text-anchor="{anc}" font-size="13" fill="#c8d4e8" paint-order="stroke" stroke="#060f22" stroke-width="4" stroke-linejoin="round">{e(m[0])}</text></a>')
    out.append("</svg>")
    return "".join(out)


def map_legend():
    """The homepage map legend, word for word."""
    return ('<div class="leg"><span class="lg-grad"><em>Quieter</em><b></b><em>Changing fastest</em></span>'
            + "".join(f'<span><i style="background:{c}"></i>{r} {n}</span>' for (lo, n, c), r in zip(BANDS, ["80+", "65–79", "50–64", "Under 50"])) + "</div>")


def heat_summary():
    tiles = tile_data()
    if not tiles:
        return ""
    n = len(tiles)
    counts = [(b, sum(1 for v in tiles.values() if band_of(v.get("s", 0)) is b)) for b in BANDS]
    bar = "".join(f'<i style="width:{c / n * 100:.1f}%;background:{b[2]}" title="{e(b[1])}: {c}"></i>' for b, c in counts if c)
    keys = "".join(f'<span><u style="background:{b[2]}"></u><b>{c}</b> {e(b[1].lower())} ({round(c / n * 100)}%)</span>' for b, c in counts if c)
    return (f'<div class="hsum"><div class="hbar">{bar}</div><div class="hkeys">{keys}</div>'
            f'<p class="small muted" style="margin:10px 0 0">Of the {n} map squares scored across London this week.</p></div>')


def heat_js():
    near = json.dumps([[m[1], m[3], m[4]] for m in AREAS], ensure_ascii=False)
    return ("""<script>/* Same popup as the homepage map: band, place, exact score with Pro, and a postcode check */
(function(){var svg=document.getElementById("ixmapsvg"),tip=document.getElementById("ixtip");if(!svg||!tip)return;
var A=""" + near + """,B=[["Changing fast","#4f9be8"],["Changing","#5fd6b8"],["Steady","#9aa3b5"],["Quiet","#6f7f9e"]],sel=null,hv=null;
function near(lat,lon){var b=null,bd=1e9;A.forEach(function(a){var d=Math.hypot((a[1]-lat)*111,(a[2]-lon)*69);if(d<bd){bd=d;b=a}});return b&&bd<3.2?b[0]:null}
function centre(k){var a=k.split("/"),x=+a[1]+.5,y=+a[2]+.5,n=8192;return{lon:x/n*360-180,lat:Math.atan(Math.sinh(Math.PI*(1-2*y/n)))*180/Math.PI}}
function pc(c){return fetch("https://api.postcodes.io/postcodes?lon="+c.lon+"&lat="+c.lat+"&radius=2000&limit=1").then(function(x){return x.json()}).then(function(j){return j.result&&j.result[0]})}
function show(r){var k=r.getAttribute("data-k"),b=B[+r.getAttribute("data-b")]||B[3],c=centre(k),nm=near(c.lat,c.lon);
 if(sel)sel.classList.remove("on");sel=r;r.classList.add("on");
 tip.innerHTML='<div class="tt-h"><i style="background:'+b[1]+'"></i>'+b[0]+'</div><div class="tt-p">'+(nm?'Around '+nm:'This area')+'</div><div class="tt-s">Exact score with <a href="/#pricing">Pro</a></div><button type="button" class="tt-b">Check a postcode here →</button>';
 tip.querySelector(".tt-b").onclick=function(){var bt=this;bt.textContent="Finding a postcode…";pc(c).then(function(q){if(!q){bt.textContent="No postcode found here";return}location.href="/?pc="+encodeURIComponent(q.postcode)+"#check"}).catch(function(){bt.textContent="Couldn’t find a postcode"})};
 if(!nm)pc(c).then(function(q){if(q&&sel===r){var e=tip.querySelector(".tt-p");if(e)e.textContent="Around "+[q.admin_ward,q.admin_district].filter(Boolean).join(", ")}}).catch(function(){});
 var w=tip.parentNode.getBoundingClientRect(),rr=r.getBoundingClientRect(),x=rr.left-w.left+rr.width/2,y=rr.top-w.top;tip.hidden=false;
 var tw=tip.offsetWidth,th=tip.offsetHeight;tip.style.left=Math.max(6,Math.min(w.width-tw-6,x-tw/2))+"px";tip.style.top=(y-th-8<6?rr.bottom-w.top+8:y-th-8)+"px"}
function hide(){tip.hidden=true;if(sel)sel.classList.remove("on");sel=null}
function hoverOK(){return matchMedia("(hover:hover)").matches}
svg.addEventListener("mouseover",function(e){var r=e.target.closest&&e.target.closest("rect.ht");if(!r||!hoverOK()||r===sel)return;clearTimeout(hv);if(tip.hidden){show(r);return}hv=setTimeout(function(){if(!tip.matches(":hover"))show(r)},350)});
svg.addEventListener("mouseout",function(e){if(e.target.closest&&e.target.closest("rect.ht"))clearTimeout(hv)});
tip.addEventListener("mouseenter",function(){clearTimeout(hv)});
svg.addEventListener("click",function(e){var r=e.target.closest&&e.target.closest("rect.ht");if(r){e.stopPropagation();show(r)}else if(!(e.target.closest&&e.target.closest(".mk")))hide()});
svg.addEventListener("mouseleave",function(e){if(hoverOK()&&!(e.relatedTarget&&tip.contains(e.relatedTarget)))setTimeout(function(){if(!tip.matches(":hover"))hide()},250)});
document.addEventListener("click",function(e){if(!tip.hidden&&!tip.contains(e.target)&&!svg.contains(e.target))hide()});
})();</script>""")


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


def changing_next(pub):
    """'Where is London changing next?': four ranked lists from this week's public top 10."""
    top = pub["areas"]
    link = lambda a: f'<a href="/london/{SLUG.get(a["n"], "")}/">{e(a["f"])}</a>'
    pw = lambda v: f"{abs(v)} pt" + ("" if abs(v) == 1 else "s")
    def col(title, sub, items, fmt, empty):
        lis = "".join(f'<li><em>{i}</em><span>{link(a)}</span><b>{fmt(a)}</b></li>' for i, a in enumerate(items, 1)) or f'<li class="none">{e(empty)}</li>'
        return f'<div class="apc cn"><div class="eyebrow">{e(title)}</div><p>{e(sub)}</p><ol>{lis}</ol></div>'
    fast = sorted([a for a in top if (a.get("c") or 0) > 0], key=lambda a: -a["c"])[:3]
    year = sorted([a for a in top if (a.get("c12") or 0) > 0], key=lambda a: -a["c12"])[:3]
    pipe = sorted(top, key=lambda a: -_num(a.get("u")))[:3]
    head = sorted([a for a in top if a["s"] >= 60 and (a.get("hd") or 0) >= 50], key=lambda a: -(a["s"] + (a.get("hd") or 0)))[:3]
    cols = (col("Speeding up", "Biggest score gains over 30 days", fast, lambda a: f"+{pw(a['c'])}", "No top-10 area rose this month.")
            + col("Rising over the year", "Biggest gains over 12 months", year, lambda a: f"+{pw(a['c12'])}", "No top-10 area is up on a year ago.")
            + col("Biggest pipelines", "Net new homes proposed in 12 months", pipe, lambda a: f"{e(a.get('u'))} homes", "—")
            + col("Momentum with headroom", "Score 60+ and prices below most of London (score · headroom)", head, lambda a: f"{a['s']} · {a['hd']}", "None this week."))
    return (f'<section class="ap-s"><div class="wrap"><div class="eyebrow">Emerging locations</div><h2>Where is London changing next?</h2>'
            f'<p class="ap-sub">Four ways to read this week’s top 10: where change is speeding up, where it has built over the year, where the most homes are planned, '
            f'and where momentum meets prices that are still below most of London. A starting point for research, not a recommendation.</p>'
            f'<div class="cns">{cols}</div>'
            f'<p class="small muted" style="margin-top:14px">Pro ranks all {pub["tracked"]} neighbourhoods this way, and every Monday Brief picks a location to watch. '
            f'<a href="/monday-brief/" style="color:var(--accent)">What’s in the brief →</a></p></div></section>')


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
</div></section>

{changing_next(pub)}

{signal_leaders(pub)}

<section class="ap-s"><div class="wrap">
<div class="eyebrow">The heat map</div><h2>All of London, square by square.</h2><p class="ap-sub">The same map as on the homepage, drawn large: every part of London scored on the same seven signals. White-ringed dots are this week’s top 10; dashed dots are also tracked, with scores in Pro. Tap a neighbourhood for its page.</p>
<div class="apc ixmap"><div class="ixh"><div><small class="mono">Spatial intelligence layer</small><h3>Greater London: tracked neighbourhoods</h3></div>{map_legend()}</div>
<div class="ixwrap">{london_map(pub)}<div id="ixtip" hidden></div></div>
<p class="maphint">Every square is about 3 km across, coloured by its Momentum score: brighter means changing faster. Hover or tap one to explore.</p></div>
{heat_summary()}
<p class="small muted" style="margin:12px 0 0">Want the score for a specific street? <a href="/#check" style="color:var(--accent)">Check any London postcode</a> for its square’s score and every significant scheme within walking distance, or <a href="/#index" style="color:var(--accent)">open the interactive map</a> to zoom in.</p>
{heat_js()}
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
<div class="apc"><div class="eyebrow">Verdict</div><ul class="vlist"><li><i style="background:#4f9be8"></i><b>80–100</b> Changing fast</li><li><i style="background:#5fd6b8"></i><b>65–79</b> Changing</li><li><i style="background:#9aa3b5"></i><b>50–64</b> Steady</li><li><i style="background:#6f7f9e"></i><b>Under 50</b> Quiet</li></ul></div>
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
<h2>Every London borough</h2><p class="ap-sub">Sorted by applications filed in the last 12 months. Approval rate and decision time cover the last 24 months, shown where at least 5 were decided. <a href="#method" style="color:var(--accent)">How these are counted</a>.</p>
<div class="apc apw"><table class="ap-t stack"><thead><tr><th>Borough</th><th class="n">Filed (12m)</th><th class="n">Homes</th><th class="n">Approved</th><th class="n">Median decision</th><th class="n">Pending</th></tr></thead><tbody>{rows}</tbody></table></div>
</div></section>
<section class="ap-s" id="method"><div class="wrap">
<div class="eyebrow">Method</div><h2>How the figures are counted</h2>
<p class="ap-sub">So you can quote them with confidence, or check them against the council’s own records.</p>
<div class="apg2">
<div class="apc"><ul class="tk">
<li><b>What counts:</b> applications recorded in the GLA Planning London Datahub as prior approval for a change of use from Class E (commercial, business and service) to homes (Class C3), plus older records whose description names Class MA.</li>
<li><b>Filed:</b> applications with a valid date in the last 12 months. <b>Homes</b> is the number of homes they propose.</li>
<li><b>Approval rate:</b> approved (including prior approval not required, started or completed) divided by approved plus refused, for applications from the last 24 months. Withdrawn and undecided applications are left out. Shown only where a borough decided at least 5.</li>
</ul></div>
<div class="apc"><ul class="tk">
<li><b>Median decision time:</b> days from the valid date to the decision, for decided applications from the last 24 months, shown where there are at least 5. The legal limit is 56 days: if the council hasn’t decided by then, the development can generally go ahead by default.</li>
<li><b>Pending:</b> applications with no decision recorded yet.</li>
<li><b>Limits:</b> figures are as recorded by each council in the Datahub, which can lag by days or weeks, and a few councils record some applications late or incompletely. Every filing links to the council’s own record. Updated every Monday.</li>
</ul></div>
</div>
<p class="small muted" style="margin-top:12px">Source: GLA Planning London Datahub. Contains public sector information licensed under the Open Government Licence v3.0. <a href="/methodology.html" style="color:var(--accent)">How the Momentum Index works</a>.</p>
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
<a class="btn ghost" href="mailto:charlie@terrayne.co?subject=Terrayne%20walkthrough" data-ev="demo_click">Book a 15-minute walkthrough</a></div></div>
</div></section>
<section class="ap-s"><div class="wrap"><h2>Questions</h2>{faq_html(qs)}
<p class="small muted" style="margin-top:22px">Source: GLA Planning London Datahub. Contains public sector information licensed under the Open Government Licence v3.0. Statuses can change, so check the council record by reference. Not legal or planning advice.</p></div></section>"""
    return page("Class MA tracker: London office-to-home approvals by borough | Terrayne",
                f"Class MA approval rates and decision times for every London borough, plus every new office-to-home filing. {nf(L.get('filed_12m'))} applications in the last 12 months. Updated {upd}.",
                "/class-ma/", body, faq_ld(qs))


# ---------------------------------------------------------------- write everything

# ---------------------------------------------------------------- product and audience pages

WALKTHROUGH = ("mailto:charlie@terrayne.co?subject=Terrayne%20walkthrough&amp;body=Hi%2C%20I%27d%20like%20a%2015-minute%20walkthrough%20of%20Terrayne."
               "%20Our%20firm%3A%20")
SAMPLE_REPORT = "/report.html?pc=CR0%201LF&amp;r=800&amp;sample=1"


def steps_html(items):
    return '<div class="stp">' + "".join(f'<div class="apc"><em>{i:02d}</em><b>{e(t)}</b><p>{d}</p></div>' for i, (t, d) in enumerate(items, 1)) + "</div>"


def ticks(items):
    return '<ul class="tk">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def big_rows(feed, n=3):
    rows = [r for r in feed.get("rows", []) if (r.get("homes") or 0) >= 10 or (r.get("commercial_m2") or 0) >= 1000 or r.get("kind") == "ma"]
    rows.sort(key=lambda r: r.get("valid", ""), reverse=True)
    return rows[:n]


def worked_example(pub, cm, feed):
    """A walkthrough of checking a site, built from this week's public data: a top-10 neighbourhood with recent filings nearby,
    two alternatives with similar scores, the borough's Class MA record, then the watchlist."""
    top = sorted(pub["areas"], key=lambda a: -a["s"])
    rows = feed.get("rows", [])
    if len(top) < 3:
        return ""
    def close(a):
        return [r for r in rows if r.get("lat") and km(a["lat"], a["lon"], r["lat"], r["lon"]) <= 2.0]
    A = max(top, key=lambda a: (len(close(a)), a["s"]))
    alts = sorted([a for a in top if a is not A], key=lambda a: abs(a["s"] - A["s"]))[:2]
    near = sorted(close(A), key=lambda r: ((r.get("homes") or 0), r.get("valid", "")), reverse=True)[:3]
    raw = A.get("raw") or {}
    names = [x.strip() for x in (A.get("b") or "").replace("LB ", "").replace("RB ", "").split("/")]
    bmap = {b.get("borough"): b for b in cm.get("boroughs", [])}
    boro = next((bmap[n] for n in names if n in bmap and bmap[n].get("approval_rate") is not None), None)
    def sch(r):
        scale = " · ".join(x for x in [f"{nf(r['homes'])} homes" if (r.get("homes") or 0) > 0 else "", f"{nf(r['commercial_m2'])} m² commercial" if (r.get("commercial_m2") or 0) >= 200 else ""] if x)
        return (f'<li><b>{e(tidy(r["site"]))}</b>: {e(scale or KIND_NAME.get(r.get("kind"), "Major scheme"))} · {e(r["status"])} · '
                f'<a href="{ref_link(r["ref"], r["borough"])}" target="_blank" rel="noopener">ref {e(r["ref"])}</a></li>')
    cmp_rows = "".join(f'<tr{" class=\"me\"" if a is A else ""}><td><b>{e(a["f"])}</b></td><td class="n" data-l="Score">{a["s"]}</td>'
                       f'<td class="n" data-l="12 months">{("+" if (a.get("c12") or 0) > 0 else "−" if (a.get("c12") or 0) < 0 else "")}{abs(a.get("c12") or 0)}</td>'
                       f'<td class="n" data-l="Homes proposed">{e(a.get("u", "—"))}</td><td class="n" data-l="Price headroom">{a.get("hd", "—")}</td>'
                       f'<td data-l="Confidence">{CONF.get((a.get("cf") or ["M"])[0], "Medium")}</td></tr>' for a in [A] + alts)
    ma_line = (f'In {e(boro["borough"])}, {round(boro["approval_rate"] * 100)}% of decided office-to-home (Class MA) applications were approved over 24 months, '
               f'with a median decision time of {nf(boro["median_days"])} days, against {round((cm.get("london") or {}).get("approval_rate", 0) * 100)}% across London. '
               f'{nf(boro.get("filed_12m"))} were filed there in the last 12 months.') if boro and boro.get("approval_rate") is not None else \
              f'The <a href="/class-ma/">Class MA tracker</a> shows how {e(A["b"])} treats office-to-home conversions compared with every other borough.'
    return f"""<section class="ap-s"><div class="wrap">
<div class="eyebrow">A worked example · this week’s real data</div><h2>Checking a site near {e(A["f"])}.</h2>
<p class="ap-sub">How a developer might use Terrayne to decide whether a site is worth pursuing. The figures update every Monday.</p>
<div class="wx">
<div class="apc"><em>01 · The area</em><p><b>{e(A["f"])}</b> scores <b>{A["s"]}/100</b> on the Momentum Index ({e(verdict(A["s"]).lower())}). In the last 12 months there were {nf(raw.get("act"))} significant planning applications within {pub.get("radius_km", 1.72):.1f} km, proposing {e(A.get("u", "—"))} net new homes. Prices are lower than in {A.get("hd", "—")}% of London.</p><a href="/london/{SLUG.get(A["n"], "")}/">The neighbourhood page →</a></div>
<div class="apc"><em>02 · What’s planned nearby</em><p>The largest recent filings around it, each with its council reference:</p><ul>{"".join(sch(r) for r in near) or "<li>No major filings in the last 60 days.</li>"}</ul><a href="/postcode-report/">A full list for any site: the Postcode Report →</a></div>
<div class="apc"><em>03 · The alternatives</em><p>Compared with the two top-10 neighbourhoods closest in score:</p><div class="apw"><table class="ap-t stack wxt"><thead><tr><th>Neighbourhood</th><th class="n">Score</th><th class="n">12 months</th><th class="n">Homes</th><th class="n">Headroom</th><th>Confidence</th></tr></thead><tbody>{cmp_rows}</tbody></table></div><a href="/#compare">Compare any three areas →</a></div>
<div class="apc"><em>04 · The planning odds</em><p>{ma_line}</p><a href="/class-ma/">Every borough →</a></div>
<div class="apc"><em>05 · Keep watching</em><p>The developer saves the site and adds {e(A["n"])} to the team watchlist. From then on, the Monday Brief covers every new filing and decision around it, and on Team an email arrives the same day a big scheme nearby is filed, approved or refused.</p><a href="/monday-brief/">What’s in the Monday Brief →</a></div>
</div>
<div class="apc wxend"><div><div class="eyebrow">What they came away with</div>
<p>In about ten minutes, without opening a single council portal: how fast the area around the site is changing, what’s planned next to it, how it compares with two alternatives, the borough’s record on office-to-home conversions, and a watch on the site from now on. Enough to decide whether it’s worth a full appraisal, a call to the agent, or a pass.</p></div>
<div class="ap-cta" style="margin-top:0"><a class="btn" href="{WALKTHROUGH}" data-ev="demo_click" data-evd="worked-example">Walk through your own site</a><a class="btn ghost" href="/account.html?signup&amp;plan=enterprise">Start with Team</a></div></div>
<p class="small muted" style="margin-top:12px">An illustration of how the tools fit together, not a recommendation about this area. Scores describe activity, not future prices.</p>
</div></section>"""


def developers_page(pub, cm, feed):
    L = cm.get("london") or {}
    rate = f"{round(L['approval_rate'] * 100)}%" if L.get("approval_rate") is not None else "—"
    bs = sorted([b for b in cm.get("boroughs", []) if b.get("decided_24m", 0) >= 5 and b.get("approval_rate") is not None],
                key=lambda b: -b.get("filed_12m", 0))[:6]
    brow = "".join(f'<tr><td><b>{e(b["borough"])}</b></td><td class="n" data-l="Filed (12m)">{nf(b["filed_12m"])}</td><td class="n" data-l="Homes proposed">{nf(b["homes_12m"])}</td>'
                   f'<td class="n" data-l="Approved">{round(b["approval_rate"] * 100)}%</td><td class="n" data-l="Median decision">{nf(b["median_days"])} days</td></tr>' for b in bs)
    qs = [("Where does the data come from?",
           "Planning applications from the GLA Planning London Datahub, which every London council feeds; station use from TfL and the Office of Rail and Road; population "
           "from the ONS; and sale prices from HM Land Registry. Every scheme comes with its council reference, so you can check the official record. "
           "<a href=\"/methodology.html#sources\">Full sources and licences</a>."),
          ("How up to date is it?",
           "Planning data is collected and processed every Monday by 7am UK time. On Team, same-day alerts check for new filings and decisions near your saved places "
           "every afternoon from Tuesday to Friday."),
          ("Can the whole team use it?",
           "Team (£99 a month) covers up to 5 people, each with their own login, sharing one watchlist and one set of saved places. Briefs, reports and PDFs can be shared "
           "within your firm, and with your clients for the project you’re advising on. For larger teams, or to get Terrayne’s data into your own systems, email hello@terrayne.co."),
          ("Can we share reports with our clients?",
           "Yes. Briefs, reports and PDFs can go to your own clients for the project you’re advising them on, as long as they keep their Terrayne source credits. On Team, "
           "reports carry your firm’s name and logo. What you can’t do is resell the data or give clients ongoing access in place of their own subscription. "
           "<a href=\"/terms.html\">See the terms</a>."),
          ("Does it show who the applicant is?",
           "No. The GLA removes personal information, including applicant and agent names, from the Datahub. Each scheme links to a search for the council’s record, "
           "where the applicant and documents are published."),
          ("Is this planning or investment advice?",
           "No. Terrayne shows what has been filed, decided and measured, from official sources, so your own research and advice are faster. It doesn’t replace "
           "professional judgement or local authority searches.")]
    feat = big_rows(feed)
    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › For developers and planning consultants</div>
<div class="eyebrow">For developers and planning consultants</div>
<h1>The planning picture around every London site.</h1>
<p class="ap-lead">Find the areas that are moving, see everything planned and decided around a site, know how each borough treats office-to-home conversions, and hear the same day when something big lands near the sites you’re watching. All from official data, with council references for every scheme.</p>
<div class="ap-cta"><a class="btn" href="{WALKTHROUGH}" data-ev="demo_click" data-evd="developers">Book a 15-minute walkthrough</a><a class="btn ghost" href="/account.html?signup">Start free</a></div>
<div class="kn k4" style="margin-top:30px"><div class="apc"><b>{nf(L.get('filed_12m'))}</b><span>office-to-home (Class MA) applications in London in 12 months</span></div><div class="apc"><b>{rate}</b><span>of decided Class MA applications approved</span></div><div class="apc"><b>{nf(L.get('median_days'))} days</b><span>median Class MA decision time</span></div><div class="apc"><b>{nf(L.get('homes_12m'))}</b><span>homes proposed through Class MA in 12 months</span></div></div>
</div></section>

<section class="ap-s"><div class="wrap">
<div class="eyebrow">How firms use it</div><h2>From shortlist to site, in four steps.</h2>
{steps_html([("Find", 'The <a href="/london/">Momentum Index</a> and its heat map show where planning, transport and population are all moving, across every part of London.'),
             ("Check", 'The postcode check and <a href="/postcode-report/">Postcode Report</a> list every significant scheme within a 5, 10 or 20-minute walk of a site, with status and council reference.'),
             ("Judge the odds", 'The <a href="/class-ma/">Class MA tracker</a> shows how often each borough approves office-to-home conversions, and how long it takes against the 56-day limit.'),
             ("Watch", 'Save your sites and patches. The <a href="/monday-brief/">Monday Brief</a> covers them every week, and Team gets an email the same day a big scheme nearby is filed, approved or refused.')])}
</div></section>

{worked_example(pub, cm, feed)}

<section class="ap-s"><div class="wrap apg">
<div class="apc"><div class="eyebrow">Office-to-home approval odds</div><h3 style="margin:8px 0 4px">The busiest boroughs for Class MA</h3>
<p class="small muted" style="margin:0 0 10px">Applications in the last 12 months; approval rate and median decision time over 24 months.</p>
<div class="apw"><table class="ap-t stack"><thead><tr><th>Borough</th><th class="n">Filed</th><th class="n">Homes</th><th class="n">Approved</th><th class="n">Median</th></tr></thead><tbody>{brow}</tbody></table></div>
<p class="small muted" style="margin:12px 0 0"><a href="/class-ma/" style="color:var(--accent)">Every borough in the Class MA tracker →</a></p></div>
<div class="apc"><div class="eyebrow">Filed recently</div><h3 style="margin:8px 0 4px">The kind of scheme Terrayne flags</h3>{feed_list(feat)}
<p class="small muted" style="margin:10px 0 0"><a href="/planning.html" style="color:var(--accent)">The full planning signal feed →</a></p></div>
</div></section>

<section class="ap-s"><div class="wrap apg dpg">
<div class="apc ix-plans" style="display:block"><div class="eyebrow">Team · £99 a month</div><h2 style="margin:6px 0 10px">Built for a small firm working on sites together.</h2>
{ticks(["Up to 5 people, each with their own login", "A shared watchlist and unlimited saved places", "Same-day email alerts when a big scheme near a saved place is filed, approved or refused",
        "The Monday Brief for every neighbourhood you follow, by email, PDF or Slack", "Unlimited postcode checks and Postcode Reports, with custom catchment sizes",
        "Reports and investment-committee memos with your firm’s name and logo, ready to share with clients", "Every tracked neighbourhood, with history and 12-month trends"])}
<div class="ap-cta"><a class="btn" href="/account.html?signup&amp;plan=enterprise">Start with Team</a><a class="btn ghost" href="/#pricing">Compare plans</a></div></div>
<div class="apc"><div class="eyebrow">Founding partners</div><h2 style="margin:6px 0 10px">Help shape what we build.</h2>
<p class="muted" style="margin:0 0 12px">We’re working closely with a small number of London developers and planning consultancies as founding partners: a guided setup, a direct line to us, and a say in what we build next.</p>
<p class="muted" style="margin:0">Ask us too about teams of more than 5, and access to Terrayne’s data for your own systems.</p>
<div class="ap-cta"><a class="btn" href="{WALKTHROUGH}" data-ev="demo_click" data-evd="developers-fp">Book a 15-minute walkthrough</a></div></div>
</div></section>

<section class="ap-s"><div class="wrap">{brief_box("", "See a real Monday Brief first.", "Pick a neighbourhood you work in and we’ll email you this week’s brief. No account or card needed.")}</div></section>

<section class="ap-s"><div class="wrap">
<h2>Questions from firms</h2>{faq_html(qs)}
<p class="small muted" style="margin-top:26px">Sources: GLA Planning London Datahub, TfL, Office of Rail and Road, ONS and HM Land Registry. Contains public sector information licensed under the Open Government Licence v3.0 (<a href="/methodology.html#sources" style="color:inherit;text-decoration:underline">full data credits</a>). Statuses can change, so check the council record by reference.</p>
</div></section>"""
    return page("For developers and planning consultants: London planning intelligence | Terrayne",
                "Find London areas that are moving, see everything planned and decided around a site, Class MA approval odds by borough, and same-day alerts near your sites.",
                "/developers/", body, faq_ld(qs))


def brief_page(pub, feed):
    top = sorted(pub["areas"], key=lambda a: -a["s"])
    keys = pub.get("keys", [])
    rows = feed.get("rows", [])
    def close(a):
        return [r for r in rows if r.get("lat") and km(a["lat"], a["lon"], r["lat"], r["lon"]) <= 2.5]
    lead = max(top, key=lambda a: (len(close(a)), a["s"])) if top else None
    near = sorted(close(lead), key=lambda r: r.get("valid", ""), reverse=True)[:2] if lead else []
    big = [r for r in big_rows(feed, 6) if r not in near][:3]
    sample = ""
    if lead:
        up = [SIG_NAME[s] for s, t in zip(keys, lead.get("tr") or []) if t == "u" and s in SIG_NAME]
        c = lead.get("c") or 0
        move = f"{'up' if c > 0 else 'down'} {_ptsw(c)}" if c else "unchanged"
        def item(r):
            scale = " · ".join(x for x in [f"{nf(r['homes'])} homes" if (r.get("homes") or 0) > 0 else "", f"{nf(r['commercial_m2'])} m² commercial" if (r.get("commercial_m2") or 0) >= 200 else ""] if x)
            return (f'<li><b>{e(tidy(r["site"]))}</b>: {e(scale)} · {e(KIND_NAME.get(r.get("kind"), "Major scheme"))} · {e(r["status"])}<br><span>{e(r.get("why") or "")}</span><br>'
                    f'<a href="{ref_link(r["ref"], r["borough"])}" target="_blank" rel="noopener">{e(r["borough"])} ref {e(r["ref"])} →</a></li>')
        sample = f"""<div class="mail"><div class="mh"><span>briefings@terrayne.co</span><span>Mon 7am</span></div>
<p class="me">Monday Brief · sample issue</p><h3>Good morning.</h3>
<p class="hl2">{e(lead['f'])} is at {lead['s']}/100 on the Momentum Index, {move} this month. Below: what’s new nearby, and the biggest new schemes across London.</p>
<div class="mc"><span class="ma">{e(lead['n'])}</span><h4>{e(lead['f'])}: {lead['s']}/100, {move} over 30 days</h4>
<p>Momentum Index <b>{lead['s']}/100</b>. {('Rising over 12 months: ' + e(', '.join(up)) + '.') if up else ''}</p>
<p><b>Decided this week</b></p><p class="dim">Approvals and refusals of significant schemes nearby appear here, in green and red, each with its council reference.</p>
<p><b>New significant filings</b></p><ul>{''.join(item(r) for r in near) or '<li>No new significant filings nearby.</li>'}</ul></div>
<p class="mt">Biggest new schemes in London</p><div class="mc"><ul>{''.join(item(r) for r in big)}</ul></div>
<p class="foot">Built from real filings in the GLA Planning London Datahub. Your brief covers the neighbourhoods on your watchlist and the places you save.</p></div>"""
    qs = [("When does it arrive?", "Every Monday by 7am UK time. When you first subscribe and pick your neighbourhoods, we email you that week’s brief straight away, so you don’t wait until Monday."),
          ("Which areas does it cover?", "The neighbourhoods on your watchlist (up to 10 on Pro), new filings near the places you save, and the biggest new schemes across London. On Team the watchlist and saved places are shared by up to 5 people."),
          ("What counts as a significant filing?", "New homes, office-to-home (Class MA) conversions, or 200 m² or more of commercial space. Paperwork on old permissions, signs, windows, cladding and similar small applications are left out, so the brief stays short."),
          ("Can I share it?", "Yes, within your organisation, and with your own clients for the project you’re advising them on, as long as it keeps its Terrayne credits. Every brief downloads as an A4 PDF, and Team can also get it in a Slack channel."),
          ("Can I stop it?", "Any time: turn it off on your profile page, or cancel your plan in a couple of clicks. You keep every past brief while your plan is active."),
          ("Can I see one first?", "Yes. Ask for a free sample on this page: pick a neighbourhood and we’ll email you this week’s brief, with no account or card needed.")]
    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › Monday Brief</div>
<div class="eyebrow">The Monday Brief</div>
<h1>What changed in your London, by 7am.</h1>
<p class="ap-lead">Nobody wants another dashboard to check. Every Monday, Terrayne emails you a short brief on the neighbourhoods and places you follow: what was filed, what was decided, which areas moved, and why each one matters. With a link to the council record for every scheme.</p>
<div class="ap-cta"><a class="btn" href="/account.html?signup&amp;plan=pro">Get the Monday Brief with Pro</a><a class="btn ghost" href="#sample">Get a free sample</a></div>
</div></section>

<section class="ap-s" style="padding-top:20px"><div class="wrap apg bpg">
<div><div class="eyebrow">What’s in it</div><h2>Seven parts, in about two minutes.</h2>
{steps_html([("Your week in one line", "How many schemes were filed and decided across your neighbourhoods, and which one moved most."),
             ("Score and direction", "Each neighbourhood’s Momentum score, how it moved, and which signals are rising or falling."),
             ("Decided this week", "Significant schemes nearby that were approved or refused, in green and red."),
             ("New filings, explained", "Every new scheme for homes, office-to-home or sizeable commercial space, with why it matters and a council link."),
             ("Near your saved places", "New filings within the walking distance you chose around each site you save."),
             ("Location to watch", "One neighbourhood each week worth a closer look, and three where momentum meets price headroom."),
             ("The biggest in London", "The three largest new schemes anywhere in London, so even a quiet week tells you something.")])}
</div>
<div><div class="eyebrow">A real sample</div><h2>Built from this week’s filings.</h2>{sample}</div>
</div></section>

<section class="ap-s"><div class="wrap">
<div class="apg3">
<div class="apc"><div class="eyebrow">Download and share</div><p class="small muted" style="margin:8px 0 0">Every brief downloads as a clean A4 PDF with the Terrayne logo, from the email or your account, to forward around your organisation or to a client. Every past brief stays in your account.</p></div>
<div class="apc"><div class="eyebrow">First brief straight away</div><p class="small muted" style="margin:8px 0 0">Subscribe, pick your neighbourhoods, and this week’s brief lands in your inbox within a minute. From then on, every Monday by 7am UK time.</p></div>
<div class="apc"><div class="eyebrow">Same-day alerts (Team)</div><p class="small muted" style="margin:8px 0 0">Team doesn’t wait for Monday: when a big scheme near a saved place is filed, approved or refused, everyone on the team gets an email that afternoon.</p></div>
</div>
</div></section>

<section class="ap-s"><div class="wrap apg">
<div class="apc"><div class="eyebrow">Pro · £29 a month</div><h3 style="margin:8px 0 8px">For one person</h3>{ticks(["The Monday Brief for up to 10 neighbourhoods", "New filings near 10 saved places", "Every past brief, as PDFs", "All tracked neighbourhoods, unlimited postcode checks and reports"])}
<div class="ap-cta"><a class="btn" href="/account.html?signup&amp;plan=pro">Get Pro</a></div></div>
<div class="apc"><div class="eyebrow">Team · £99 a month</div><h3 style="margin:8px 0 8px">For up to 5 people</h3>{ticks(["Everything in Pro, shared across your team", "Unlimited saved places", "Same-day alerts near your saved places", "The brief in Slack, and branded reports"])}
<div class="ap-cta"><a class="btn ghost" href="/account.html?signup&amp;plan=enterprise">Get Team</a></div></div>
</div></section>

<section class="ap-s" id="sample"><div class="wrap">{brief_box("", "Get a free sample Monday Brief.", "Pick a neighbourhood and we’ll email you this week’s brief: what was filed, what moved and why it matters. No account or card needed.")}</div></section>

<section class="ap-s"><div class="wrap"><h2>Questions about the brief</h2>{faq_html(qs)}</div></section>"""
    return page("The Monday Brief: London planning and property changes, every Monday by 7am | Terrayne",
                "A short email every Monday on the London neighbourhoods and sites you follow: new filings, approvals and refusals, score moves and why each one matters.",
                "/monday-brief/", body, faq_ld(qs))


def report_page(pub, feed):
    qs = [("What area does it cover?", "The postcode you choose and a walking distance around it: 400 m (about 5 minutes), 800 m (about 10) or 1.6 km (about 20)."),
          ("How current is it?", "It uses the latest weekly data at the moment you buy it, and shows the date of each source. It’s a snapshot: it doesn’t update afterwards."),
          ("Is it a substitute for local authority searches or a survey?", "No. It summarises what has been filed and measured around a postcode, from official open data, to help your research. It isn’t a legal search, a survey or advice."),
          ("How do I pay?", "By card through Stripe, £12 per report, with no subscription. Terrayne never sees your card details."),
          ("Can I give it to a client?", "Yes. You can share it within your organisation and with your own client for their project, as long as it keeps its Terrayne source credits. It can’t be resold or published online."),
          ("What if something goes wrong?", "If a report fails to load or is wrong because of a fault on our side, email hello@terrayne.co and we’ll fix it or refund you."),
          ("I need lots of reports.", "Pro (£29 a month) includes unlimited postcode checks and reports. Team adds reports and investment-committee memos with your firm’s name and logo.")]
    body = f"""<section class="ap-h"><div class="wrap">
<div class="crumb"><a href="/">Terrayne</a> › Postcode Report</div>
<div class="eyebrow">The Postcode Report · £12</div>
<h1>Everything planned around one London postcode.</h1>
<p class="ap-lead">Every significant planning application within a 5, 10 or 20-minute walk, with its status and council reference. How many homes and new residents that adds up to, how fast the area is changing, how local prices compare with the rest of London, and a short summary of demand and risks. As a PDF, in about a minute.</p>
<div class="ap-cta"><a class="btn" href="/report.html" data-ev="report_start" data-evd="report-page">Get a report · £12</a><a class="btn ghost" href="{SAMPLE_REPORT}">See a sample report</a></div>
</div></section>

<section class="ap-s" style="padding-top:20px"><div class="wrap apg rpg">
<div class="apc"><div class="eyebrow">What’s inside</div>{ticks(["<b>Every significant scheme nearby</b>: new homes, office-to-home conversions and commercial space, each with its status, size and council reference",
        "<b>What it adds up to</b>: homes proposed and the number of new residents that could mean",
        "<b>The area’s Momentum score</b>, with all seven signals and whether each is rising or falling",
        "<b>Price headroom</b>: how local prices compare with the rest of London",
        "<b>Demand, opportunities and risks</b>, in plain English",
        "<b>Sources and dates</b> for every figure, and a clean A4 PDF to save"])}</div>
<div><div class="eyebrow">How it works</div><h2>Three steps, one minute.</h2>
{steps_html([("Enter a postcode", "Any London postcode, and pick a walking distance: 400 m, 800 m or 1.6 km."),
             ("See the preview free", "The summary and the three largest schemes nearby, before you pay anything."),
             ("Unlock for £12", "Pay by card and get the full report straight away: every scheme, the signals, opportunities, risks and the PDF.")])}</div>
</div></section>

<section class="ap-s"><div class="wrap">
<h2>Who it’s for</h2>
<div class="apg3">
<div class="apc"><div class="eyebrow">Buying or renting</div><p class="small muted" style="margin:8px 0 0">See what’s planned around a home before you commit: new blocks, conversions next door, shops and offices on the way.</p></div>
<div class="apc"><div class="eyebrow">Agents</div><p class="small muted" style="margin:8px 0 0">Back up a valuation or a listing with what’s planned within walking distance, and how the area compares with London.</p></div>
<div class="apc"><div class="eyebrow">Developers and investors</div><p class="small muted" style="margin:8px 0 0">A fast first look at a site’s surroundings and pipeline before you spend on a full appraisal. Need several? Pro includes unlimited reports.</p></div>
</div>
<div class="ap-cta"><a class="btn" href="/report.html" data-ev="report_start" data-evd="report-page-2">Get a report · £12</a><a class="btn ghost" href="/#check">Try a free postcode check first</a></div>
</div></section>

<section class="ap-s"><div class="wrap"><h2>Questions about the report</h2>{faq_html(qs)}
<p class="small muted" style="margin-top:26px">Built from the GLA Planning London Datahub, TfL, Office of Rail and Road, ONS and HM Land Registry data (<a href="/methodology.html#sources" style="color:inherit;text-decoration:underline">full data credits</a>). Scores describe activity, not future prices, and aren’t investment advice.</p>
</div></section>"""
    return page("The £12 Postcode Report: everything planned around a London postcode | Terrayne",
                "Every significant planning application within a 5, 10 or 20-minute walk of any London postcode, with council references, the Momentum score and price headroom. £12, no subscription.",
                "/postcode-report/", body, faq_ld(qs))


KIND_NAME = {"ma": "Office-to-home (Class MA)", "major": "Major scheme", "res": "New homes", "com": "Commercial space"}


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
    for slug, html_ in (("developers", developers_page(pub, cm, feed)), ("monday-brief", brief_page(pub, feed)), ("postcode-report", report_page(pub, feed))):
        (ROOT / slug).mkdir(exist_ok=True)
        (ROOT / slug / "index.html").write_text(html_)
    (ROOT / "class-ma").mkdir(exist_ok=True)
    (ROOT / "class-ma" / "index.html").write_text(classma_page(cm))
    lastmod = pub["generated"]
    urls = ["/", "/london/", "/developers/", "/monday-brief/", "/postcode-report/", "/class-ma/", "/planning.html", "/methodology.html", "/about.html", "/report.html"] + [f"/london/{m[5]}/" for m in AREAS]
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + "".join(f"  <url><loc>{SITE}{u}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    (ROOT / "robots.txt").write_text("User-agent: *\nDisallow: /admin.html\nDisallow: /account.html\nDisallow: /unsubscribe.html\n\n"
                                     f"Sitemap: {SITE}/sitemap.xml\n")
    return {"area_pages": len(AREAS), "with_scores": len(by), "sitemap_urls": len(urls)}


if __name__ == "__main__":
    print(write_all())
