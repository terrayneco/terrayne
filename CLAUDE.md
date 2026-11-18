# Terrayne website — instructions for Claude

This repo is the live website at https://terrayne.co (GitHub Pages, `main` branch).

## Source of truth
The master copy is on the Mac: `~/Library/Mobile Documents/com~apple~CloudDocs/TYE/website/terrayne.html`
(logo in `assets/logo.jpg` beside it). An auto-sync (launchd `co.terrayne.sync`) copies it here as
`index.html` and pushes whenever it is saved. Edit `terrayne.html`, not `index.html`, or the next
sync will overwrite your change. If you do edit here, copy `index.html` back to `terrayne.html` too.

## Every time you make a change
1. Run `git pull` first, so you're editing the latest version.
2. Make the edit in `terrayne.html` (the whole site is one page; the logo is `assets/logo.jpg`).
3. Check it still works on phones, tablets and desktops — don't break the responsive CSS block at the end of the `<style>` tag.
4. Commit with a short plain-English message and `git push` to `main` straight away. Changes are not live until they are pushed.
5. Tell Charlie it's pushed and will be live on terrayne.co in about a minute (hard refresh: Cmd+Shift+R).

## Momentum Index (real data)
- Scores come from `scripts/momentum.py` (method + weights in its docstring): 4 planning signals from the GLA Planning London Datahub, plus 3 official-statistics signals from `scripts/signals.py` (TfL/ORR station usage, ONS LSOA population, HM Land Registry resale prices; locations from NaPTAN, ONS Open Geography, OS Code-Point Open). Downloads cache in `.cache/` (git-ignored). If a source fails, it is skipped and listed under `errors` in the output.
- `scripts/publish.py` is the entry point: writes `data/momentum.json` with the free top 10 only, plus (via explore.py) `data/feed.json`, the live planning feed and sample brief, and (with Supabase env vars) stores the full snapshot + weekly briefs in Supabase for paying users. Never commit the full all-areas data publicly.
- The home page loads `data/momentum.json` live and also embeds a snapshot between `/*MI*/` markers.
- The GitHub Action `.github/workflows/momentum.yml` runs publish.py every Monday 05:15 UTC and emails briefs.
- Refresh by hand: `python3 scripts/publish.py --html "$HOME/Library/Mobile Documents/com~apple~CloudDocs/TYE/website/terrayne.html"`, then sync/push.

## Cities
- London: full index (planning + official stats). Manchester (beta): `scripts/city.py` builds data/manchester/ from brownfield registers (scored on hectares), Land Registry new-build sales, ORR rail, ONS population, LR resale prices. Greater Manchester has no open planning-applications feed.
- `scripts/signals.py` has a CITIES config; `signals.configure(city)` switches every loader. Add a city there + in `CITY_AREAS` (city.py) + `CITYCFG`/`CK_CITIES` in the page JS.
- Birmingham is shown as "coming soon" (Paris removed: different planning system, not yet in progress).

## Accounts (Supabase + Stripe)
- `account.html`, `admin.html`, `report.html`, `about.html`, `planning.html` (Class MA tracker + signal feed; copies the homepage styles, nav and those two sections), `methodology.html`, `terms.html`, `privacy.html`, `assets/config.js`, `assets/report-core.js`, `supabase/` live in THIS repo only (methodology.html copies the homepage's styles and nav; regenerate it if those change) (not in the iCloud folder); edit them here.
- Setup steps are in `SETUP.md`. `assets/config.js` holds only the public Supabase URL + anon key; never put secret keys in the repo.
- Neighbourhoods are listed in `AREAS` in the script; add or move one there.

## Don't
- Don't delete or rename `CNAME` — it connects the site to terrayne.co.
- Don't create other branches; push to `main`.

## Style
Dark navy (#060d1a), large white type, muted grey text, rounded corners. Branding says "property intelligence".
