// POST { plan: "pro"|"enterprise", interval: "month"|"year" } -> { url } of a Stripe Checkout page.
// ("enterprise" is shown on the site as "Team".) No free trial: subscriptions start and are charged straight away.
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
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer,
    line_items: [{ price, quantity: 1 }],
    allow_promotion_codes: true,
    billing_address_collection: "auto",
    tax_id_collection: { enabled: true },
    customer_update: { name: "auto", address: "auto" },
    client_reference_id: me.profile.id,
    subscription_data: { metadata: { user_id: me.profile.id } },
    custom_text: {
      submit: { message: "Cancel any time from your Terrayne account. You keep access until the end of the period you've paid for." },
    },
    success_url: `${SITE}/account.html?checkout=success#billing`,
    cancel_url: `${SITE}/account.html?checkout=cancelled#billing`,
  });
  return json({ url: session.url });
});
