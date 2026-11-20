// POST { plan: "pro"|"enterprise", interval: "month"|"year" } -> { url } of a Stripe Checkout page.
// POST { check: true } -> { trial: boolean }: whether this account still qualifies for the free trial.
// ("enterprise" is shown on the site as "Team".) First-time subscribers get a 14-day free trial. A card is
// required but not charged until the trial ends; the webhook ends the trial early if that card has already
// been used on another account (one free trial per card).
import { cors, json, currentUser, ensureCustomer, PRICES, stripe, SITE } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  const { plan, interval, check } = await req.json().catch(() => ({}));
  if (check) {
    // Never subscribed (no Stripe customer, or no past subscriptions) = still eligible.
    if (!me.profile.stripe_customer_id) return json({ trial: true });
    const had = await stripe.subscriptions.list({ customer: me.profile.stripe_customer_id, status: "all", limit: 1 });
    return json({ trial: had.data.length === 0 });
  }
  const price = PRICES[`${plan}:${interval}`];
  if (!price) return json({ error: "Unknown plan." }, 400);
  if (me.profile.team_owner) return json({ error: "Your plan is managed by your team owner." }, 400);

  const customer = await ensureCustomer(me.profile);
  // Already subscribed: send them to the portal to switch plan instead of a second subscription.
  if (me.profile.stripe_subscription_id && ["active", "trialing", "past_due"].includes(me.profile.status)) {
    const portal = await stripe.billingPortal.sessions.create({ customer, return_url: `${SITE}/account.html#billing` });
    return json({ url: portal.url });
  }
  // One trial per customer: anyone who has had a subscription before pays from day one.
  const past = await stripe.subscriptions.list({ customer, status: "all", limit: 1 });
  const trial = past.data.length === 0;
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer,
    line_items: [{ price, quantity: 1 }],
    allow_promotion_codes: true,
    billing_address_collection: "auto",
    tax_id_collection: { enabled: true },
    customer_update: { name: "auto", address: "auto" },
    client_reference_id: me.profile.id,
    subscription_data: {
      metadata: { user_id: me.profile.id },
      ...(trial ? { trial_period_days: 14 } : {}),
    },
    custom_text: {
      submit: {
        message: trial
          ? "Your 14-day free trial starts today. Your card won't be charged until it ends, and you can cancel any time before then from your Terrayne account. One free trial per person."
          : "Cancel any time from your Terrayne account. You keep access until the end of the period you've paid for.",
      },
    },
    success_url: `${SITE}/account.html?checkout=success#billing`,
    cancel_url: `${SITE}/account.html?checkout=cancelled#billing`,
  });
  return json({ url: session.url });
});
