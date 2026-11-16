// POST { session, postcode } -> { ok } if that Checkout session paid for this postcode's report (valid 30 days).
import { cors, json, stripe } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const { session, postcode } = await req.json().catch(() => ({}));
  if (!/^cs_[A-Za-z0-9_]+$/.test(String(session || ""))) return json({ ok: false });
  try {
    const s = await stripe.checkout.sessions.retrieve(session);
    const pc = String(postcode || "").toUpperCase().replace(/\s+/g, " ").trim();
    const fresh = Date.now() / 1000 - s.created < 30 * 86400;
    return json({ ok: s.payment_status === "paid" && s.metadata?.postcode === pc && fresh, radius: Number(s.metadata?.radius || 800) });
  } catch (_) {
    return json({ ok: false });
  }
});
