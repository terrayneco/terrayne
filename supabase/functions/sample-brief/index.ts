// Free sample Monday Brief for one neighbourhood, by email only (no account needed).
//   POST { email, area, updates, source, website }  -> stores the sign-up and emails this week's brief for that area
//   POST { unsubscribe: "<token>" }                  -> stops all emails to that address
// Anyone can call it, so in the Supabase dashboard turn OFF "Verify JWT" for this function.
// One sample per email address, ever. Spam is also limited by the database (300 per day in total) and a hidden form field.
// Self-contained (no shared files), so it can be pasted straight into the Supabase dashboard editor.
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const SITE = Deno.env.get("SITE_URL") ?? "https://terrayne.co";
const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });
const cors = {
  "Access-Control-Allow-Origin": SITE,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

const FROM = Deno.env.get("BRIEF_FROM") ?? "Terrayne <briefings@terrayne.co>";
const AREAS = ["Nine Elms", "Stratford", "Canada Water", "Whitechapel", "King’s Cross", "Croydon", "Old Kent Road", "Elephant",
  "Wembley", "Brent Cross", "Tottenham Hale", "Ilford", "Greenwich Pen.", "Woolwich", "Lewisham", "Hammersmith", "Ealing", "Isle of Dogs",
  "Royal Docks", "Barking Riverside", "Old Oak", "Earls Court", "Walthamstow", "Colindale", "Thamesmead", "Romford"];
const esc = (s: string) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

function email(area: string, week: string, title: string, body: string, token: string) {
  const d = new Date(week + "T07:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  const btn = (href: string, label: string, solid: boolean) =>
    `<a href="${href}" style="display:inline-block;margin:0 8px 8px 0;padding:11px 20px;border-radius:999px;font-weight:600;font-size:14px;text-decoration:none;${solid ? "background:#ffffff;color:#060d1a" : "border:1px solid #2a3b60;color:#ffffff"}">${label}</a>`;
  return `<div style="background:#060d1a;padding:32px 16px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff">
<div style="max-width:620px;margin:0 auto">
<img src="https://terrayne.co/assets/email-logo.png" width="180" height="60" alt="Terrayne" style="display:block;border:0;color:#ffffff;font-size:18px;margin:0 0 14px">
<p style="letter-spacing:.2em;font-size:11px;color:#9fd0ff;text-transform:uppercase;margin:0 0 8px">Sample Monday Brief · ${d}</p>
<h1 style="font-size:24px;margin:0 0 10px">Here’s what’s changing in ${esc(area)}.</h1>
<p style="font-size:14px;line-height:1.6;color:#c8d4e8;margin:0 0 20px">This is the brief Pro subscribers got this Monday for one neighbourhood. Pro sends one like it for every area on your watchlist, every Monday by 7am, plus alerts when something new is filed near the places you save.</p>
<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:18px 20px;margin:0 0 20px">
<p style="font-size:12px;color:#8c9ab3;margin:0 0 4px">${esc(area)}</p><h2 style="font-size:17px;margin:0 0 8px">${esc(title)}</h2>
<div style="font-size:14px;line-height:1.55;color:#c8d4e8">${body}</div></div>
${btn(`${SITE}/account.html?signup&plan=pro`, "Get Pro, £29 a month", true)}${btn(`${SITE}/#check`, "Check a postcode free", false)}
<p style="font-size:11px;color:#52617f;margin:22px 0 0;line-height:1.6">Built from the GLA Planning London Datahub. Statuses can change; check the council register by reference. Scores describe activity, not future prices, and aren’t investment advice.<br>
You’re getting this because someone asked for a sample brief at terrayne.co with this address. <a href="${SITE}/unsubscribe.html?t=${token}" style="color:#8c9ab3">Stop emails from Terrayne</a>.</p>
</div></div>`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  let b: Record<string, unknown> = {};
  try { b = await req.json(); } catch { return json({ error: "Bad request" }, 400); }

  // One-click unsubscribe
  if (typeof b.unsubscribe === "string") {
    if (!/^[0-9a-f-]{36}$/i.test(b.unsubscribe)) return json({ error: "That link isn’t valid." }, 400);
    const { data: row } = await admin.from("brief_signups").select("email").eq("token", b.unsubscribe).maybeSingle();
    if (!row) return json({ error: "That link isn’t valid." }, 404);
    await admin.from("brief_signups").update({ unsubscribed: true, updates: false }).eq("email", row.email);
    return json({ ok: true });
  }

  if (b.website) return json({ ok: true });                               // hidden field: bots fill it in, people don't
  const addr = String(b.email ?? "").trim().toLowerCase().slice(0, 200);
  const area = String(b.area ?? "");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(addr)) return json({ error: "Please enter a valid email address." }, 400);
  if (!AREAS.includes(area)) return json({ error: "Please choose a neighbourhood." }, 400);

  const { data: prior } = await admin.from("brief_signups").select("id").eq("email", addr).eq("unsubscribed", true).limit(1);
  if (prior?.length) return json({ error: "This address asked us to stop emailing it. Email hello@terrayne.co to start again." }, 400);

  // One sample per email address, ever: the sample shows what Pro is like; Pro sends one for every area each week.
  const { data: had } = await admin.from("brief_signups").select("id").eq("email", addr).limit(1);
  if (had?.length) return json({ error: "We’ve already sent a sample brief to this address. Pro sends one for every area on your watchlist, every Monday: terrayne.co/#pricing" }, 409);

  const { data: brief } = await admin.from("briefs").select("week,title,body").eq("area", area).order("week", { ascending: false }).limit(1).maybeSingle();
  if (!brief) return json({ error: "The first brief for this neighbourhood arrives on Monday. Please choose another neighbourhood for now, or come back after Monday." }, 409);

  const ins = await admin.from("brief_signups").insert({
    email: addr, area, updates: b.updates === true, source: String(b.source ?? "").slice(0, 120),
  }).select("token").single();
  if (ins.error) {
    const tooMany = /too many/i.test(ins.error.message);
    return json({ error: tooMany ? "We’ve already sent a sample to this address today. Check your inbox (and spam folder)." : "Something went wrong. Please try again." }, tooMany ? 429 : 500);
  }

  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to: addr, subject: `Your sample Monday Brief: ${area}`, html: email(area, brief.week, brief.title, brief.body, ins.data.token) }),
  });
  if (!r.ok) return json({ error: "We couldn’t send the email just now. Please try again in a few minutes." }, 502);
  return json({ ok: true });
});
