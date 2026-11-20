// POST { plan: "pro"|"enterprise", interval: "month"|"year" } -> { url } of a Stripe Checkout page.
// ("enterprise" is shown on the site as "Team".) First-time subscribers get a 14-day free trial with no card
// needed; if no payment method is added by the end, Stripe cancels the subscription and the webhook moves
// them back to the free plan.
import { cors, json, currentUser, ensureCustomer, PRICES, stripe, SITE } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  const { plan, interval } = await req.json().catch(() => ({}));
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
      ...(trial ? { trial_period_days: 14, trial_settings: { end_behavior: { missing_payment_method: "cancel" } } } : {}),
    },
    ...(trial ? { payment_method_collection: "if_required" as const } : {}),
    success_url: `${SITE}/account.html?checkout=success#billing`,
    cancel_url: `${SITE}/account.html?checkout=cancelled#billing`,
  });
  return json({ url: session.url });
});
