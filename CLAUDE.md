# Terrayne website — instructions for Claude

This repo is the live website at https://terrayne.co (GitHub Pages, `main` branch).

## Source of truth
The master copy is on the Mac: `~/Library/Mobile Documents/com~apple~CloudDocs/TYE/website/terrayne.html`
(logo in `assets/logo.jpg` beside it). An auto-sync (launchd `co.terrayne.sync`) copies it here as
`index.html` and pushes whenever it is saved. Edit `terrayne.html`, not `index.html`, or the next
sync will overwrite your change. If you do edit here, copy `index.html` back to `terrayne.html` too.
When giving Charlie the Mac copy command, pin it to the pushed commit (`https://raw.githubusercontent.com/terrayneco/terrayne/<full sha>/index.html`), never `/main/`: raw.githubusercontent caches `main` for minutes, and a stale copy gets auto-synced back over the live site.

## Every time you make a change
1. Run `git pull` first, so you're editing the latest version.
2. Make the edit in `terrayne.html` (the whole site is one page; the logo is `assets/logo.jpg`).
3. Check it still works on phones, tablets and desktops — don't break the responsive CSS block at the end of the `<style>` tag.
4. Commit with a short plain-English message and `git push` to `main` straight away. Changes are not live until they are pushed.
5. Tell Charlie it's pushed and will be live on terrayne.co in about a minute (hard refresh: Cmd+Shift+R).

## Momentum Index (real data)
- Scores come from `scripts/momentum.py` (method + weights in its docstring): 4 planning signals from the GLA Planning London Datahub, plus 3 official-statistics signals from `scripts/signals.py` (TfL/ORR station usage, ONS LSOA population, HM Land Registry resale prices; locations from NaPTAN, ONS Open Geography, OS Code-Point Open). Downloads cache in `.cache/` (git-ignored). If a source fails, it is skipped and listed under `errors` in the output.
- `scripts/publish.py` is the entry point: writes `data/momentum.json` with the free top 10 only, plus (via explore.py) `data/feed.json`, the live planning feed and sample brief, and (with Supabase env vars) stores the full snapshot + weekly briefs in Supabase for paying users. Never commit the full all-areas data publicly.
- Confidence: `confidence()` in momentum.py gives every area and tile `cf: ["H"|"M"|"L", [reasons]]` (missing signals + thin samples). Shown via `cfb()` on the homepage, report.html and account.html; explained at methodology.html#confidence.
- Direction of travel: `c12` (12-month score change) and `tr` (per-signal "u"/"f"/"d") on every area and tile, from `trend()` in momentum.py; shown with `trw()` on the homepage, compare, report and account.
- Signal feed rows carry `why` and `next` (explore.why()); planning.html links each ref to a search for the council record.
- The postcode and compare boxes accept place names (`placePC()`: postcodes.io places -> nearest postcode).
- To refresh public data midweek without touching Supabase/briefs: run the workflow with `data_only: true`.
- Compare (`#compare` on the homepage): up to 3 areas side by side. Free: the public top-10 neighbourhoods. Postcodes (from data/tiles.json): paid plans only.
- The home page loads `data/momentum.json` live and also embeds a snapshot between `/*MI*/` markers.
- The GitHub Action `.github/workflows/momentum.yml` runs publish.py every Monday 05:15 UTC and emails briefs.
- Refresh by hand: `python3 scripts/publish.py --html "$HOME/Library/Mobile Documents/com~apple~CloudDocs/TYE/website/terrayne.html"`, then sync/push.

## Growth pages and tracking
- Momentum Index page: `london/index.html` (pages.py `london_page`) is the Index's own page and the site menu's "Index" link: top-10 leaderboard, movers, SVG map (river from index.html's `TH`), the 7 signals and weights, benchmarks, back-test (data/backtest.json), how to read a score, who uses it, plans, FAQ + Dataset JSON-LD, plus an automatic "This week in brief" summary (`week_summary`), signal leaders, trend sparklines from `data/history.json` (weekly public top-10 scores, appended by pages.py `update_history`; first two points derived from c12/c), a heat map of `data/tiles.json` (same colour scale as the homepage `hcol`) and a copyable citation line. Public top 10 only; the other 8 stay locked.
- Product/audience pages, also built by pages.py every Monday: `/developers/` (`developers_page`: Class MA odds from classma.json, recent big schemes from feed.json, Team + founding partners), `/monday-brief/` (`brief_page`: anatomy + a sample built from real feed filings), `/postcode-report/` (`report_page`, the £12 report). Nav "Developers & Class MA" links to /developers/. Terms allow sharing briefs/reports within the customer’s organisation and with their own clients for that project (credits kept; no resale or ongoing client access).
- SEO pages: `scripts/pages.py` builds `london/index.html`, `london/<slug>/index.html` (18 neighbourhoods; full detail only for the public top 10, the rest show planning context and a Pro prompt, so no paid data leaks), `class-ma/index.html`, `sitemap.xml` and `robots.txt` from the public data files. publish.py runs it every Monday; the workflow commits the output. Edit the generator, never the generated HTML. It copies the head/nav styles from methodology.html, so re-run `python3 scripts/pages.py` after changing those.
- Sample brief: `assets/brief.js` renders any `<div data-brief-signup data-area="...">` box; it posts to the `sample-brief` Edge Function (email + area, no account; one sample per email address, ever). Stop-emails page: `unsubscribe.html`. Sign-ups are in Supabase `brief_signups` and on admin.html.
- Funnel counts: `assets/track.js` (`tyTrack(name, detail)`, plus automatic clicks on signup/plan/report links and any element with `data-ev`). Anonymous rows in Supabase `events`; no cookies, storage or personal data (keep it that way, and keep privacy.html in step). Shown on admin.html via `admin_growth()`. publish.py deletes events older than 2 years. Page views come from Cloudflare Web Analytics.
- History: the `snapshots` and `briefs` tables are the long-term data asset; never delete from them. admin.html has "Download full history" (needs `supabase/2026-11-history.sql`) for a monthly backup.
- Monday brief PDF: `brief.html?week=YYYY-MM-DD[&all=1][&pdf=1]` shows the signed-in Pro/Team user's brief (watchlist areas + saved-place alerts) as an A4 page; "Download PDF" saves a real A4 PDF via `assets/pdf.js` (tyPDF: html2pdf.js, MIT, self-hosted in assets/vendor; desktop layout forced via .pdfcopy; falls back to print). report.html uses it too. Linked from the brief email (send-briefs) and account.html → Monday briefs. account.html?next=brief.html… returns there after sign-in (only brief.html is allowed).
- Monday brief contents (publish.py `brief_for`): per area a one-line score + 12-month trend, "Decided this week" (approved/refused significant schemes by decision_date, falls back to a scan if that field isn't searchable), new filings with a "why it matters" line (explore.why) and a council link. Each row's `data` holds name, move, items, decided, london (top 3 new London schemes); send-briefs and brief.html build the headline summary and the London section from it. Dedupe via data.refs / drefs / lrefs.
- Monday brief filings (publish.py `brief_item`/`BRIEF_WANT`/`NOISE`): only new homes, Class MA, or 200+ m² commercial; condition paperwork, signs, windows, cladding etc. and impossible dates are dropped; sorted by homes then floorspace. Same rule for saved-place alerts.
- Same-day alerts (Team): `scripts/instant.py`, run Tue–Fri 16:40 UTC by `.github/workflows/alerts.yml` (manual runs default to dry run). Big filings (10+ homes, 1,000+ m², Class MA) and approvals/refusals near Team saved places, deduped via the `instant_alerts` table, emailed by send-briefs `{instant}`. Members can turn them off (`profiles.instant_email`, account → Profile). Needs `supabase/2026-11-alerts.sql`.
- First brief: account.html `firstBrief()` calls send-briefs `{first:true}` (user JWT) once a Pro/Team user has a watchlist; the function sends the latest week's brief once per account (`first_briefs` table).
- New public pages should load `assets/track.js` (after config.js) and the Cloudflare beacon.

## Cities
- London: full index (planning + official stats). Manchester (beta): `scripts/city.py` builds data/manchester/ from brownfield registers (scored on hectares), Land Registry new-build sales, ORR rail, ONS population, LR resale prices. Greater Manchester has no open planning-applications feed.
- `scripts/signals.py` has a CITIES config; `signals.configure(city)` switches every loader. Add a city there + in `CITY_AREAS` (city.py) + `CITYCFG`/`CK_CITIES` in the page JS.
- Site is deliberately London-focused: Manchester stays as an "experimental" Index tab only; no Birmingham/international promotion on the site.

## Accounts (Supabase + Stripe)
- `account.html`, `admin.html`, `report.html`, `about.html`, `planning.html` (Class MA tracker + signal feed; copies the homepage styles, nav and those two sections), `methodology.html`, `terms.html`, `privacy.html`, `assets/config.js`, `assets/report-core.js`, `supabase/` live in THIS repo only (methodology.html copies the homepage's styles and nav; regenerate it if those change) (not in the iCloud folder); edit them here.
- Setup steps are in `SETUP.md`. `assets/config.js` holds only the public Supabase URL + anon key; never put secret keys in the repo.
- Neighbourhoods are listed in `AREAS` in the script; add or move one there.

## Don't
- Don't delete or rename `CNAME` — it connects the site to terrayne.co.
- Don't create other branches; push to `main`.

## Style
Dark navy (#060d1a), large white type, muted grey text, rounded corners. Branding says "property intelligence".
Wording: "Monday Brief" (capitalised product name), "Postcode Report", "Momentum Index" (the index) / "Momentum score" (an area's number), "office-to-home (Class MA)" (never "office-to-resi"), "saved places" (not saved postcodes/properties), "watchlist", plans Free / Pro £29 / Team £99 / £12 report, "by 7am UK time every Monday".
