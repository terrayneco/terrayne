# Terrayne website — instructions for Claude

This repo is the live website at https://terrayne.co (GitHub Pages, `main` branch).

## Every time you make a change
1. Run `git pull` first, so you're editing the latest version.
2. Make the edit (the whole site is `index.html`; the logo is `assets/logo.jpg`).
3. Check it still works on phones, tablets and desktops — don't break the responsive CSS block at the end of the `<style>` tag.
4. Commit with a short plain-English message and `git push` to `main` straight away. Changes are not live until they are pushed.
5. Tell Charlie it's pushed and will be live on terrayne.co in about a minute (hard refresh: Cmd+Shift+R).

## Don't
- Don't delete or rename `CNAME` — it connects the site to terrayne.co.
- Don't create other branches; push to `main`.

## Style
Dark navy (#060d1a), large white type, muted grey text, rounded corners. Branding says "property intelligence".
