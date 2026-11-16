// POST -> cancels any subscription immediately and deletes the user and their data.
import { cors, json, currentUser, admin, stripe } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  const p = me.profile;
  if (p.stripe_subscription_id) {
    try { await stripe.subscriptions.cancel(p.stripe_subscription_id); } catch (_) { /* already gone */ }
  }
  await admin.from("profiles").update({ team_owner: null }).eq("team_owner", p.id); // release team members
  const { error } = await admin.auth.admin.deleteUser(p.id); // cascades to profile, watchlist, invites
  if (error) return json({ error: error.message }, 500);
  return json({ deleted: true });
});
