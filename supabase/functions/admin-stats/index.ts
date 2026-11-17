// Admin panel data. Only profiles with is_admin = true may call it.
// POST {}                                   -> dashboard stats
// POST { action: "comp", user_id, plan }    -> give a free (complimentary) plan: "pro" | "enterprise" | "free"
import Stripe from "npm:stripe@14.25.0";
import { admin, cors, currentUser, json, stripe } from "../_shared/common.ts";

const DAY = 86400000;
const monthly = (p: Stripe.Price, qty: number) =>
  ((p.unit_amount ?? 0) * qty) / 100 / (p.recurring?.interval === "year" ? 12 * (p.recurring.interval_count ?? 1) : (p.recurring?.interval_count ?? 1));

async function allUsers() {
  const out: { id: string; email?: string; created_at: string; last_sign_in_at?: string; email_confirmed_at?: string }[] = [];
  for (let page = 1; page < 50; page++) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    if (error || !data.users.length) break;
    out.push(...data.users);
    if (data.users.length < 1000) break;
  }
  return out;
}

async function stripeStats() {
  if (!Deno.env.get("STRIPE_SECRET_KEY")) return null;
  const subs: Stripe.Subscription[] = [];
  for await (const s of stripe.subscriptions.list({ status: "all", limit: 100 })) {
    subs.push(s);
    if (subs.length >= 5000) break;
  }
  const live = subs.filter((s) => ["active", "trialing", "past_due"].includes(s.status));
  const mrr = live.reduce((t, s) => t + s.items.data.reduce((a, i) => a + monthly(i.price, i.quantity ?? 1), 0), 0);
  const since30 = Date.now() / 1000 - 30 * 86400;
  const byPrice: Record<string, { count: number; mrr: number; nickname: string; interval: string; amount: number }> = {};
  for (const s of live) for (const i of s.items.data) {
    const k = i.price.id;
    byPrice[k] ??= { count: 0, mrr: 0, nickname: i.price.nickname ?? "", interval: i.price.recurring?.interval ?? "", amount: (i.price.unit_amount ?? 0) / 100 };
    byPrice[k].count++; byPrice[k].mrr += monthly(i.price, i.quantity ?? 1);
  }
  const paid: Stripe.Invoice[] = [];
  for await (const inv of stripe.invoices.list({ status: "paid", limit: 100, created: { gte: Math.floor((Date.now() - 365 * DAY) / 1000) } })) {
    paid.push(inv);
    if (paid.length >= 5000) break;
  }
  const byMonth: Record<string, number> = {};
  for (const inv of paid) {
    const m = new Date(inv.created * 1000).toISOString().slice(0, 7);
    byMonth[m] = (byMonth[m] ?? 0) + inv.amount_paid / 100;
  }
  const last30 = paid.filter((i) => i.created >= since30).reduce((t, i) => t + i.amount_paid / 100, 0);
  const churned = subs.filter((s) => s.status === "canceled" && (s.canceled_at ?? 0) >= since30).length;
  const startLive = live.length + churned;
  return {
    currency: (paid[0]?.currency ?? "gbp").toUpperCase(),
    mrr, arr: mrr * 12, active: live.length,
    trialing: subs.filter((s) => s.status === "trialing").length,
    past_due: subs.filter((s) => s.status === "past_due").length,
    cancelling: live.filter((s) => s.cancel_at_period_end).length,
    new_30d: subs.filter((s) => s.created >= since30).length,
    churned_30d: churned,
    churn_rate_30d: startLive ? churned / startLive : 0,
    revenue_30d: last30,
    revenue_12m: paid.reduce((t, i) => t + i.amount_paid / 100, 0),
    arpu: live.length ? mrr / live.length : 0,
    by_price: Object.values(byPrice),
    by_month: byMonth,
    recent: paid.slice(0, 12).map((i) => ({ date: new Date(i.created * 1000).toISOString(), amount: i.amount_paid / 100, email: i.customer_email, number: i.number, url: i.hosted_invoice_url })),
  };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me || !me.profile.is_admin) return json({ error: "Admins only." }, 403);
  const body = await req.json().catch(() => ({}));

  if (body.action === "comp") {
    if (!["free", "investor", "pro", "enterprise"].includes(body.plan)) return json({ error: "Bad plan" }, 400);
    const { data: t } = await admin.from("profiles").select("status").eq("id", body.user_id).single();
    if (t && ["active", "trialing", "past_due"].includes(t.status)) return json({ error: "This user pays through Stripe; change their plan there." }, 400);
    const upd = body.plan === "free" ? { plan: "free", status: "none" } : { plan: body.plan, status: "comp" };
    const { error } = await admin.from("profiles").update(upd).eq("id", body.user_id);
    return error ? json({ error: error.message }, 500) : json({ ok: true });
  }

  const [users, profilesR, watchR, reqR, snapR, briefR, sendR, billing, sessR] = await Promise.all([
    allUsers(),
    admin.from("profiles").select("id,email,full_name,company,job_title,plan,status,billing_interval,current_period_end,cancel_at_period_end,team_owner,brief_email,is_admin,created_at"),
    admin.from("watchlist").select("user_id,area"),
    admin.from("access_requests").select("*").order("created_at", { ascending: false }).limit(200),
    admin.from("snapshots").select("generated").order("generated", { ascending: false }).limit(1),
    admin.from("briefs").select("week").order("week", { ascending: false }).limit(2000),
    admin.from("brief_sends").select("*").order("created_at", { ascending: false }).limit(12),
    stripeStats().catch((e) => ({ error: (e as Error).message })),
    admin.rpc("admin_session_stats"),
  ]);
  const profiles = profilesR.data ?? [], watch = watchR.data ?? [];
  const authById = new Map(users.map((u) => [u.id, u]));
  // Devices and IPs per account over 7 days. Missing if the SQL function has not been created yet.
  const sess = new Map(((sessR.data ?? []) as { user_id: string; sessions: number; ips: number; devices: number }[]).map((r) => [r.user_id, r]));
  const SHARE = (r?: { ips: number; devices: number }) => !!r && (r.ips >= 4 || r.devices >= 4);
  const wCount: Record<string, number> = {}, perUser: Record<string, number> = {};
  for (const w of watch) { wCount[w.area] = (wCount[w.area] ?? 0) + 1; perUser[w.user_id] = (perUser[w.user_id] ?? 0) + 1; }
  const now = Date.now();
  const effective = (p: typeof profiles[number]) => {
    const own = p.plan !== "free" && ["active", "trialing", "past_due", "comp"].includes(p.status);
    if (own) return p.plan;
    const o = p.team_owner && profiles.find((x) => x.id === p.team_owner);
    return o && o.plan === "enterprise" && ["active", "trialing", "past_due", "comp"].includes(o.status) ? "enterprise" : "free";
  };
  const weeks: Record<string, number> = {};
  for (const u of users) {
    const d = new Date(u.created_at); d.setUTCHours(0, 0, 0, 0); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const k = d.toISOString().slice(0, 10); weeks[k] = (weeks[k] ?? 0) + 1;
  }
  const briefWeeks = [...new Set((briefR.data ?? []).map((b) => b.week))];
  return json({
    generated_at: new Date().toISOString(),
    users: {
      total: users.length,
      confirmed: users.filter((u) => u.email_confirmed_at).length,
      new_7d: users.filter((u) => now - +new Date(u.created_at) < 7 * DAY).length,
      new_30d: users.filter((u) => now - +new Date(u.created_at) < 30 * DAY).length,
      active_7d: users.filter((u) => u.last_sign_in_at && now - +new Date(u.last_sign_in_at) < 7 * DAY).length,
      active_30d: users.filter((u) => u.last_sign_in_at && now - +new Date(u.last_sign_in_at) < 30 * DAY).length,
      by_plan: profiles.reduce((t: Record<string, number>, p) => { const e = effective(p); t[e] = (t[e] ?? 0) + 1; return t; }, {}),
      comp: profiles.filter((p) => p.status === "comp").length,
      team_members: profiles.filter((p) => p.team_owner).length,
      brief_opt_in: profiles.filter((p) => p.brief_email).length,
      signups_by_week: weeks,
    },
    engagement: {
      watchlists: Object.keys(perUser).length,
      avg_watchlist: Object.keys(perUser).length ? watch.length / Object.keys(perUser).length : 0,
      top_areas: Object.entries(wCount).sort((a, b) => b[1] - a[1]).slice(0, 12),
    },
    data: { latest_snapshot: snapR.data?.[0]?.generated ?? null, brief_weeks: briefWeeks.length, latest_brief_week: briefWeeks[0] ?? null, sends: sendR.data ?? [] },
    billing,
    requests: reqR.data ?? [],
    sessions_ok: !sessR.error,
    people: profiles.map((p) => ({
      ...p, effective_plan: effective(p), watchlist: perUser[p.id] ?? 0,
      last_sign_in_at: authById.get(p.id)?.last_sign_in_at ?? null, confirmed: !!authById.get(p.id)?.email_confirmed_at,
      devices_7d: sess.get(p.id)?.devices ?? 0, ips_7d: sess.get(p.id)?.ips ?? 0, sharing: SHARE(sess.get(p.id)),
    })).sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)),
  });
});
