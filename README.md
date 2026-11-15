# Terrayne — terrayne.co

The website for Terrayne, property intelligence (launching in London).

Live at **https://terrayne.co**, hosted free on GitHub Pages.

## What's in here

| File | What it is |
|---|---|
| `index.html` | The entire website: one page, with all styling and interactivity built in |
| `assets/logo.jpg` | The Terrayne logo shown in the top-left of the menu bar |
| `CNAME` | Tells GitHub Pages to serve the site at terrayne.co. **Don't delete or rename it.** |
| `README.md` | This file |
| `CLAUDE.md` | Instructions Claude Code follows when editing this site |

## Making changes

The master copy lives on the Mac at
`iCloud Drive/TYE/website/terrayne.html` (with `assets/logo.jpg` beside it).

Saving that file triggers an auto-sync on the Mac (`~/Library/LaunchAgents/co.terrayne.sync.plist`,
script `~/Library/Scripts/terrayne-sync.sh`) that copies it here as `index.html`, commits and
pushes to `main`. terrayne.co updates about a minute later. Log: `~/Library/Logs/terrayne-sync.log`.

**Don't upload files through the GitHub website**: the next save on the Mac will overwrite them.

## Domain setup (Wix DNS)

- A records (`@`): 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153
- CNAME (`www`): terrayneco.github.io
