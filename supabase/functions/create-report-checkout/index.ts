// POST { postcode, radius } -> { url } of a £12 Stripe Checkout for one Postcode Report. No account needed.
import { cors, json, stripe, SITE } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const { postcode, radius } = await req.json().catch(() => ({}));
  const pc = String(postcode || "").toUpperCase().replace(/\s+/g, " ").trim();
  if (!/^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$/.test(pc)) return json({ error: "Please enter a full UK postcode." }, 400);
  const r = [400, 800, 1600].includes(Number(radius)) ? Number(radius) : 800;
  const price = Deno.env.get("PRICE_REPORT");
  if (!price) return json({ error: "Reports aren't on sale yet." }, 503);
  const q = `pc=${encodeURIComponent(pc)}&r=${r}`;
  const s = await stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [{ price, quantity: 1 }],
    metadata: { postcode: pc, radius: String(r) },
    allow_promotion_codes: true,
    success_url: `${SITE}/report.html?${q}&session={CHECKOUT_SESSION_ID}`,
    cancel_url: `${SITE}/report.html?${q}`,
  });
  return json({ url: s.url });
});
