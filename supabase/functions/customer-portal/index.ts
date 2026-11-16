// POST -> { url } of the Stripe Customer Portal (change plan, cancel, update card, invoices).
import { cors, json, currentUser, ensureCustomer, stripe, SITE } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  if (me.profile.team_owner) return json({ error: "Your plan is managed by your team owner." }, 400);
  const customer = await ensureCustomer(me.profile);
  const s = await stripe.billingPortal.sessions.create({ customer, return_url: `${SITE}/account.html#billing` });
  return json({ url: s.url });
});
