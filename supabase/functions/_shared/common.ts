import Stripe from "npm:stripe@14.25.0";
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

export const SITE = Deno.env.get("SITE_URL") ?? "https://terrayne.co";
export const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, {
  apiVersion: "2024-06-20",
  httpClient: Stripe.createFetchHttpClient(),
});
export const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});

// Stripe price IDs, set as function secrets.
export const PRICES: Record<string, string | undefined> = {
  "investor:month": Deno.env.get("PRICE_INV_MONTH"),
  "investor:year": Deno.env.get("PRICE_INV_YEAR"),
  "pro:month": Deno.env.get("PRICE_PRO_MONTH"),
  "pro:year": Deno.env.get("PRICE_PRO_YEAR"),
  "enterprise:month": Deno.env.get("PRICE_ENT_MONTH"),
  "enterprise:year": Deno.env.get("PRICE_ENT_YEAR"),
};
export function planForPrice(priceId: string): [string, string] | null {
  for (const [k, v] of Object.entries(PRICES)) if (v === priceId) return k.split(":") as [string, string];
  return null;
}

export const cors = {
  "Access-Control-Allow-Origin": SITE,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

// Returns the signed-in user's profile, or null.
export async function currentUser(req: Request) {
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer /, "");
  if (!token) return null;
  const { data, error } = await admin.auth.getUser(token);
  if (error || !data.user) return null;
  const { data: profile } = await admin.from("profiles").select("*").eq("id", data.user.id).single();
  return profile ? { user: data.user, profile } : null;
}

export async function ensureCustomer(profile: { id: string; email: string; full_name: string; stripe_customer_id: string | null }) {
  if (profile.stripe_customer_id) return profile.stripe_customer_id;
  const c = await stripe.customers.create({ email: profile.email, name: profile.full_name || undefined, metadata: { user_id: profile.id } });
  await admin.from("profiles").update({ stripe_customer_id: c.id }).eq("id", profile.id);
  return c.id;
}
