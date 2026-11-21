# Terrayne: accounts, payments and emails

How the live site is connected to Supabase, Stripe and Resend, and how to set it up again from scratch.
Status (November 2026): all of this is done and live. Use this file to rebuild, move projects or hand over.

Never paste a secret key (Supabase service_role, Stripe `sk_`/`rk_`, `whsec_`, Resend `re_`, Turnstile secret)
into the website, a chat or a commit. They live only in Supabase secrets and GitHub Actions secrets.
Price IDs, the Supabase URL, the publishable key and the Turnstile site key are not secret.

## 1. Supabase (logins and data)
1. supabase.com → New project → name `terrayne`, region **London (eu-west-2)**. Tick "Enable automatic RLS".
2. SQL Editor → New query → paste all of `supabase/schema.sql` → Run (accept the "destructive operations" warning on a new project).
3. Authentication → URL Configuration: Site URL `https://terrayne.co/account.html`; add the same address as the only Redirect URL.
4. Project Settings → API Keys: copy the **Project URL** (just `https://<ref>.supabase.co`, nothing after `.co`)
   and the **Publishable key** (`sb_publishable_…`) into the values (not the comments) of `assets/config.js`.
5. **Emails (required, or nobody outside your Supabase team can sign up):** Authentication → Emails → Set up SMTP →
   Resend (or SMTP Settings: host `smtp.resend.com`, port `465`, user `resend`, password = a Resend sending key),
   sender `noreply@terrayne.co`, name `Terrayne`. Then Authentication → Rate Limits → emails per hour `100`.
6. Authentication → Sign In / Providers → Email: keep "Confirm email" on; minimum password length **10**.

## 2. Stripe (payments)
Build everything in the **sandbox** first, test it, then repeat in **live** mode.
1. Product catalogue → add products (currency **GBP**):
   - Terrayne Investor: £19/month and £190/year
   - Terrayne Professional: £79/month and £790/year
   - Terrayne Enterprise: £399/month and £3,990/year
   - Postcode Report: £12 one-off
   Live mode: use "Copy to live mode" on each product. Live price IDs are different from sandbox ones.
2. Copy the seven price IDs (`price_…`). Open a product → ⋯ next to a price → Copy price ID.
3. Coupons → Founding member: £30 off, applies to Terrayne Professional, duration **forever**, max **50** redemptions,
   promotion code `FOUNDING`, "first-time orders only". (Stripe can't limit a coupon to one price, so it also works on
   Professional yearly.) Coupons are not copied to live; recreate them.
4. Customer portal: payment methods on; invoices on; cancellations on, **at end of billing period**, survey on,
   no retention coupon; customer email not editable; tax ID editable; upgrades and downgrades on with all three
   subscription products (both prices each), promotion codes **off**, increases apply immediately, decreases and
   shorter billing periods apply at the end of the period, prorate and invoice immediately.
5. Settings → Billing → Subscriptions and emails: renewal, expiring-card and failed-payment emails on; link to a
   Stripe-hosted page; include a link to the customer portal. Payments needing confirmation: send the
   Stripe-hosted confirmation link.
6. Webhooks → Add destination → Your account, **Snapshot**, events `checkout.session.completed`,
   `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted` →
   Webhook endpoint `https://<ref>.supabase.co/functions/v1/stripe-webhook`. Copy the signing secret (`whsec_…`).
7. API keys → Create restricted key → "Building your own integration" → Custom permissions:
   Checkout Sessions, Customers, Customer portal, Subscriptions: **Write**; Invoices, Products, Prices: **Read**;
   everything else None. Copy the key (`rk_…`).
8. Statement descriptor `TERRAYNE.CO`, shortened `TERRAYNE`. Stripe Tax, invoicing and Managed Payments: off
   (revisit with an accountant before VAT registration).

## 3. Resend (all email)
1. resend.com → Domains → add `terrayne.co`, region EU (Ireland). Add the DNS records it shows at the registrar
   (Wix → Domains → ⋯ → Manage DNS records): TXT `resend._domainkey`, CNAME `send`, CNAME `rsend`,
   TXT `_dmarc` = `v=DMARC1; p=none;`. Use Resend's copy buttons; host names without `.terrayne.co`.
2. API Keys → one key for the server functions (`RESEND_API_KEY`) and, if not using the Supabase integration,
   one for Supabase SMTP. Sending access only.
3. Free plan: 100 emails a day, 3,000 a month, shared between sign-up emails and Monday Briefs.

## 4. Server functions
Secrets: Supabase → Edge Functions → Secrets (easier than the command line, and keys stay out of shell history):
`PRICE_INV_MONTH`, `PRICE_INV_YEAR`, `PRICE_PRO_MONTH`, `PRICE_PRO_YEAR`, `PRICE_ENT_MONTH`, `PRICE_ENT_YEAR`,
`PRICE_REPORT`, `STRIPE_SECRET_KEY` (the `rk_` key), `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`,
`CRON_SECRET` (any long random string; keep a copy for GitHub), `SITE_URL` = `https://terrayne.co`,
`BRIEF_FROM` = `Terrayne <briefings@terrayne.co>`. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are built in.

Deploy (Mac Terminal, once: `brew install supabase/tap/supabase`):
```
cd ~ && git clone https://github.com/terrayneco/terrayne.git terrayne-deploy && cd terrayne-deploy
supabase login
supabase link --project-ref <ref>
supabase functions deploy create-checkout && \
supabase functions deploy customer-portal && \
supabase functions deploy delete-account && \
supabase functions deploy admin-stats && \
supabase functions deploy slack-test && \
supabase functions deploy team-invite && \
supabase functions deploy create-report-checkout --no-verify-jwt && \
supabase functions deploy verify-report --no-verify-jwt && \
supabase functions deploy stripe-webhook --no-verify-jwt && \
supabase functions deploy send-briefs --no-verify-jwt && echo "ALL DEPLOYED"
```
Answer Yes to each prompt. "Docker is not running" can be ignored. To redeploy one function after a code change:
`cd ~/terrayne-deploy && git pull && supabase functions deploy <name>` (add `--no-verify-jwt` for the ones above).

## 5. Weekly job (GitHub Actions)
`.github/workflows/momentum.yml` runs every Monday 05:15 UTC: rebuilds the index, stores briefs in Supabase,
emails paying users and publishes the free top 10 to `data/`.
Repo → Settings → Secrets and variables → Actions: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
(Supabase → API Keys → Legacy → service_role), `CRON_SECRET` (same value as in Supabase).
Run it by hand: Actions → "Weekly Momentum Index and Monday Brief" → Run workflow (tick "Email" to send briefs).
A healthy run ends with `stored snapshot and 18 briefs for <date>`.

## 6. Admins
Sign up at terrayne.co/account.html, then in the Supabase SQL Editor:
`update public.profiles set is_admin = true where email = 'you@example.com';`
Check who is admin: `select email from public.profiles where is_admin;`
Admin panel: terrayne.co/admin.html (revenue, users, plans, payments, access requests, free "comp" plans).
Shared-login detector: the Users table shows devices and networks per account over 7 days and flags 4+.
It needs the `admin_session_stats` function at the end of `supabase/schema.sql` (run that part in the SQL Editor).

## 7. Going live / switching Stripe accounts
1. Complete Stripe's business verification.
2. Repeat section 2 in live mode (products copied; coupon, portal, emails, webhook and restricted key recreated).
3. Replace the 7 `PRICE_…` secrets, `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in Supabase.
4. Unlink any test accounts from old Stripe customers:
   `update public.profiles set plan='free', status='none', billing_interval=null, current_period_end=null,
   cancel_at_period_end=false, stripe_customer_id=null, stripe_subscription_id=null where email='you@example.com';`
5. Test for free with a one-use 100%-off coupon on Investor, then cancel that subscription immediately in Stripe
   and delete the coupon.

## 8. Test checklist
- Sign up with an email that is not on the Supabase team → confirmation arrives from Terrayne.
- Upgrade → plan shows in the account within seconds → "Manage subscription" opens the portal →
  cancelling shows "Cancels on …". If the plan doesn't change: Stripe → Webhooks → Event deliveries.
- Profile → Delete account (never on the admin account).
- Admin panel loads with live numbers.

## 9. Security
- Two-factor login on GitHub, Stripe, Supabase, Resend, Wix and the Gmail behind the admin account.
- CAPTCHA (optional, stops bot sign-ups): Cloudflare Turnstile → add widget for `terrayne.co` (Managed) →
  put the **site key** in `assets/config.js` as `turnstileSiteKey: "…"` and push → then Supabase →
  Authentication → Attack Protection → enable CAPTCHA, provider Turnstile, paste the **secret key**.
  Do it in that order: turning it on in Supabase first blocks every sign-in until the site sends tokens.
- Keep admins to a minimum. If a key leaks, rotate it in that service and update the secret.

## Notes
- The homepage master copy is `terrayne.html` in iCloud (see CLAUDE.md). After any change made to `index.html`
  on GitHub, copy it back:
  `curl -s https://raw.githubusercontent.com/terrayneco/terrayne/main/index.html -o "$HOME/Library/Mobile Documents/com~apple~CloudDocs/TYE/website/terrayne.html"`
- The webhook re-reads each subscription from Stripe, so event order and Stripe API versions don't matter.

## Pricing change, November 2026: Free / Pro £29 / Team £99

Internal plan keys stay the same: `pro` is sold as **Pro**, `enterprise` is sold as **Team**. `investor` is no longer sold;
existing Investor subscribers keep working.

1. **Stripe → Product catalogue → Terrayne Professional**: rename to **Terrayne Pro**. Add price **£29 / month** (recurring)
   and **£290 / year**. Copy both price IDs (`price_…`). Archive the old £79 and £790 prices.
2. **Terrayne Enterprise**: rename to **Terrayne Team**. Add **£99 / month** and **£990 / year**. Copy both IDs. Archive £399 and £3,990.
3. **Terrayne Investor**: archive the product (existing subscribers are unaffected).
4. **Coupons**: delete or archive the `FOUNDING` promotion code.
5. **Settings → Billing → Customer portal → Products**: replace the old prices with the four new ones (Pro and Team, monthly
   and yearly), remove Investor. Make sure customers can **update payment methods** (needed to keep a plan after the trial).
6. **Supabase → Edge Functions → Secrets**: set `PRICE_PRO_MONTH`, `PRICE_PRO_YEAR`, `PRICE_ENT_MONTH`, `PRICE_ENT_YEAR` to the four new IDs.
7. Deploy the checkout function: `supabase functions deploy create-checkout` (no free trial; "cancel any time" note on checkout)
8. **Supabase → SQL Editor**: run `supabase/2026-11-pricing.sql` (updates upgrade messages; limits unchanged).
9. Test: sign up with a new email, choose Pro, check Stripe checkout shows £29/month.


## Growth: sample-brief sign-ups, funnel counts, neighbourhood pages (November 2026)
1. **Supabase → SQL Editor**: paste and run `supabase/2026-11-growth.sql` (creates `brief_signups`, `events` and the `admin_growth` function the admin page uses).
2. **Supabase → Edge Functions → Deploy a new function** named `sample-brief`, paste `supabase/functions/sample-brief/index.ts`, and turn **off** "Verify JWT" (anyone can request a sample; one sample per email address, and the database limits it to 300 a day). It's self-contained, so paste just that one file. It uses the existing `RESEND_API_KEY` secret, so no new secrets.
3. Test: on terrayne.co, fill in "Get a free sample Monday Brief" with your own email. You should get the email within a minute, and see the sign-up on admin.html under **Growth funnel**.
4. **Google Search Console** (search.google.com/search-console): add `terrayne.co`, then submit `https://terrayne.co/sitemap.xml` so Google finds the neighbourhood pages and the Class MA page.

Pages: `london/`, `london/<slug>/` and `class-ma/` are generated by `scripts/pages.py` (run inside publish.py every Monday, and committed by the workflow with `sitemap.xml` and `robots.txt`). Edit the generator, not the generated HTML.

## History backup (November 2026)
Every Monday's full snapshot and briefs are stored only in Supabase (the free plan has no backups).
1. **Supabase → SQL Editor**: run `supabase/2026-11-history.sql` (lets admin accounts read snapshots and briefs).
2. Once a month: open **admin.html → Data & briefs → Download full history**, and save the file to iCloud Drive (e.g. `TYE/backups/`). The page warns you if it's been over 35 days.
3. When there's revenue, Supabase's paid plan adds automatic daily backups.

## Monday Brief PDF (November 2026)
The brief email now has a "Download this brief as a PDF" button (to `brief.html`). To switch it on, update the **send-briefs** function:
**Supabase → Edge Functions → send-briefs → Code → index.ts**, replace it with `supabase/functions/send-briefs/index.ts` from the repo, and click **Deploy** (leave the `_shared` file as it is; "Verify JWT" stays off).
