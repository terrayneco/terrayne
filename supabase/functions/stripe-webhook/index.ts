// Stripe -> Supabase: keeps each profile's plan in step with its subscription.
// Deploy with --no-verify-jwt; Stripe signs requests with STRIPE_WEBHOOK_SECRET instead.
import Stripe from "npm:stripe@14.25.0";
import { admin, planForPrice, stripe } from "../_shared/common.ts";

const crypto = Stripe.createSubtleCryptoProvider();

async function sync(sub: Stripe.Subscription) {
  const customer = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
  const item = sub.items.data[0];
  const mapped = item ? planForPrice(item.price.id) : null;
  const live = ["active", "trialing", "past_due"].includes(sub.status);
  const update = {
    plan: live && mapped ? mapped[0] : "free",
    billing_interval: mapped ? mapped[1] : null,
    status: sub.status,
        current_period_end: (() => { const e = (sub as any).current_period_end ?? (item as any)?.current_period_end; return e ? new Date(e * 1000).toISOString() : null; })(),
    cancel_at_period_end: sub.cancel_at_period_end,
    stripe_subscription_id: live ? sub.id : null,
  };
  const { data } = await admin.from("profiles").update(update).eq("stripe_customer_id", customer).select("id");
  if (!data?.length && sub.metadata?.user_id) {
    await admin.from("profiles").update({ ...update, stripe_customer_id: customer }).eq("id", sub.metadata.user_id);
  }
}

Deno.serve(async (req) => {
  const sig = req.headers.get("Stripe-Signature");
  const body = await req.text();
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(body, sig!, Deno.env.get("STRIPE_WEBHOOK_SECRET")!, undefined, crypto);
  } catch (e) {
    return new Response(`Bad signature: ${(e as Error).message}`, { status: 400 });
  }
  switch (event.type) {
    case "checkout.session.completed": {
      const s = event.data.object as Stripe.Checkout.Session;
      if (s.subscription) await sync(await stripe.subscriptions.retrieve(s.subscription as string));
      break;
    }
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
      await sync(event.data.object as Stripe.Subscription);
      break;
  }
  return new Response(JSON.stringify({ received: true }), { headers: { "Content-Type": "application/json" } });
});
