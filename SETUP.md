# Turning on accounts and subscriptions

Everything is built. These steps connect it to your own Supabase, Stripe and Resend accounts.
Do them in order. Stripe **test mode** is fine to start; switch to live keys when ready.

## 1. Supabase (logins and data)
1. supabase.com → New project → name `terrayne`, region London (eu-west-2).
2. SQL Editor → New query → paste all of `supabase/schema.sql` → Run.
3. Authentication → URL Configuration:
   - Site URL: `https://terrayne.co/account.html`
   - Redirect URLs: add `https://terrayne.co/account.html`
4. Project Settings → API: copy **Project URL** and **anon public** key into `assets/config.js`.
5. Keep the **service_role** key secret (never put it in the website).

## 2. Stripe (payments)
1. Products → add **Terrayne Professional** with two prices: £79/month and £790/year.
2. Add **Terrayne Enterprise** with two prices: £399/month and £3,990/year.
3. Copy the four price IDs (`price_...`).
4. Settings → Billing → Customer portal: enable "Customers can switch plans" (add both products and all four prices), "Cancel subscriptions" (at end of billing period), "Update payment methods" and "Invoice history". Save.
5. Developers → Webhooks → Add endpoint:
   `https://<project-ref>.supabase.co/functions/v1/stripe-webhook`
   Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. Copy the signing secret (`whsec_...`).

## 3. Resend (Monday emails)
1. resend.com → Domains → add `terrayne.co.uk` (the domain your emails use) and add the DNS records it shows at your domain registrar.
2. API Keys → create one.

## 4. Deploy the server functions
Install the Supabase CLI (`brew install supabase/tap/supabase`), then from this folder:
```
supabase login
supabase link --project-ref <project-ref>
supabase secrets set STRIPE_SECRET_KEY=sk_... STRIPE_WEBHOOK_SECRET=whsec_... \
  PRICE_PRO_MONTH=price_... PRICE_PRO_YEAR=price_... PRICE_ENT_MONTH=price_... PRICE_ENT_YEAR=price_... \
  RESEND_API_KEY=re_... CRON_SECRET=<any long random string> SITE_URL=https://terrayne.co \
  BRIEF_FROM="Terrayne <briefings@terrayne.co.uk>"
supabase functions deploy create-checkout
supabase functions deploy customer-portal
supabase functions deploy delete-account
supabase functions deploy admin-stats
supabase functions deploy stripe-webhook --no-verify-jwt
supabase functions deploy send-briefs --no-verify-jwt
```

## 5. Weekly job (GitHub)
Repo → Settings → Secrets and variables → Actions → add:
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CRON_SECRET` (same value as above).
Then Actions → "Weekly Momentum Index and Monday brief" → Run workflow (leave "send" off) to fill the first week of briefs and history.

## 6. Make yourself an admin
1. Create your own account at terrayne.co/account.html.
2. Supabase → SQL Editor → run: `update public.profiles set is_admin = true where email = 'YOUR EMAIL';`
3. Open terrayne.co/admin.html for users, revenue (MRR, ARR, churn), signups, plan mix, payments, access requests, and to give pilots free (“comp”) plans.

## 7. Test
1. terrayne.co/account.html → create an account → confirm the email.
2. Subscription → Upgrade to Professional → pay with test card `4242 4242 4242 4242`, any future date, any CVC.
3. Check: plan shows Professional, watchlist works, briefs and history appear, "Manage subscription" opens Stripe, cancelling shows "Cancels on …".
4. Run the workflow with "send" on to receive a test brief.
