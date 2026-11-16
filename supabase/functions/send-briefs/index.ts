// Emails this week's Monday brief to every paying user with a watchlist.
// Called by the weekly GitHub Action: POST with header "x-cron-secret: <CRON_SECRET>", body { week: "YYYY-MM-DD" }.
// Deploy with --no-verify-jwt (protected by CRON_SECRET instead).
import { admin, SITE } from "../_shared/common.ts";

const FROM = Deno.env.get("BRIEF_FROM") ?? "Terrayne <briefings@terrayne.co.uk>";
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

function html(name: string, week: string, items: { area: string; title: string; body: string }[], alerts: Alert[] = []) {
  const d = new Date(week + "T07:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return `<div style="background:#060d1a;padding:32px 16px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff">
<div style="max-width:620px;margin:0 auto">
<p style="letter-spacing:.2em;font-size:11px;color:#9fd0ff;text-transform:uppercase;margin:0 0 8px">Terrayne · Monday Brief · ${d}</p>
<h1 style="font-size:24px;margin:0 0 20px">Good morning${name ? ", " + esc(name.split(" ")[0]) : ""}.</h1>
${items.map((b) => `<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:18px 20px;margin:0 0 12px">
<p style="font-size:12px;color:#8c9ab3;margin:0 0 4px">${esc(b.area)}</p><h2 style="font-size:17px;margin:0 0 8px">${esc(b.title)}</h2>
<div style="font-size:14px;line-height:1.55;color:#c8d4e8">${b.body}</div></div>`).join("")}
${alertsHtml(alerts)}
<p style="font-size:13px;color:#8c9ab3;margin:24px 0 0"><a href="${SITE}/account.html#briefs" style="color:#9fd0ff">Open all briefs</a> · <a href="${SITE}/account.html#profile" style="color:#9fd0ff">Email settings</a></p>
<p style="font-size:11px;color:#52617f">Built from the GLA Planning London Datahub. Statuses can change; check the council register by reference.</p>
</div></div>`;
}

// 7am London time on the brief's Monday, whether the UK is on GMT or BST.
function sevenAmLondon(week: string) {
  const noon = new Date(week + "T12:00:00Z");
  const zone = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", timeZoneName: "short" })
    .formatToParts(noon).find((p) => p.type === "timeZoneName")?.value ?? "GMT";
  return `${week}T07:00:00${zone === "BST" ? "+01:00" : "Z"}`;
}

type Alert = { label: string; postcode: string; radius_m: number; items: { site: string; units: number; kind: string; status: string; ref: string; lpa: string; dist: number }[] };

function alertsHtml(alerts: Alert[]) {
  if (!alerts.length) return "";
  return `<h2 style="font-size:17px;margin:22px 0 10px">New near your saved places</h2>` + alerts.map((a) => `<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:16px 18px;margin:0 0 12px">
<p style="font-size:12px;color:#8c9ab3;margin:0 0 6px">${esc(a.label || a.postcode)} · within ${a.radius_m} m</p>
<ul style="margin:0;padding-left:18px;font-size:14px;color:#c8d4e8">${a.items.map((i) => `<li style="margin-bottom:6px"><b style="color:#fff">${esc(i.site)}</b>${i.units > 0 ? ` · ${i.units} homes` : ""} · ${esc(i.kind)} · ${esc(i.status)} <span style="color:#8c9ab3">(${esc(i.lpa)} ref ${esc(i.ref)}, ${i.dist} m away)</span></li>`).join("")}</ul></div>`).join("");
}

async function slack(hook: string, week: string, items: { area: string; title: string }[], alerts: Alert[]) {
  if (!/^https:\/\/hooks\.slack\.com\/services\//.test(hook)) return;
  const lines = items.map((b) => `• *${b.area}*: ${b.title}`);
  const al = alerts.flatMap((a) => a.items.slice(0, 5).map((i) => `• ${a.label || a.postcode}: ${i.site}${i.units > 0 ? ` (${i.units} homes)` : ""}, ${i.status}`));
  const text = `*Terrayne Monday Brief · ${week}*\n${lines.join("\n")}${al.length ? `\n\n*New near your saved places*\n${al.join("\n")}` : ""}\n<${SITE}/account.html#briefs|Open the full brief>`;
  await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }).catch(() => {});
}

async function alertsFor(uid: string, week: string): Promise<Alert[]> {
  const { data: me } = await admin.from("profiles").select("team_owner").eq("id", uid).single();
  const owners = [uid, ...(me?.team_owner ? [me.team_owner] : [])];
  const { data: places } = await admin.from("saved_places").select("id,label,postcode,radius_m").in("owner", owners);
  if (!places?.length) return [];
  const { data: rows } = await admin.from("alerts").select("place_id,items").eq("week", week).in("place_id", places.map((p) => p.id));
  return (rows ?? []).filter((r) => (r.items as unknown[]).length).map((r) => {
    const p = places.find((x) => x.id === r.place_id)!;
    return { label: p.label, postcode: p.postcode, radius_m: p.radius_m, items: r.items as Alert["items"] };
  });
}

Deno.serve(async (req) => {
  if (req.headers.get("x-cron-secret") !== Deno.env.get("CRON_SECRET")) return new Response("forbidden", { status: 403 });
  const { week } = await req.json();
  const { data: briefs } = await admin.from("briefs").select("area,title,body").eq("week", week);
  if (!briefs?.length) return new Response(JSON.stringify({ sent: 0, reason: "no briefs" }));
  const byArea = new Map(briefs.map((b) => [b.area, b]));
  const { data: users } = await admin.from("profiles").select("id,email,full_name,brief_email,slack_webhook,team_owner").eq("brief_email", true);
  let sent = 0;
  const failed: string[] = [];
  for (const u of users ?? []) {
    const { data: plan } = await admin.rpc("effective_plan", { uid: u.id });
    if (plan === "free" || !plan) continue;
    const alerts = await alertsFor(u.id, week);              // Investor and up: alerts near saved places
    let items: { area: string; title: string; body: string }[] = [];
    if (plan === "pro" || plan === "enterprise") {           // Monday brief is Professional and up
      const { data: wl } = await admin.from("watchlist").select("area").eq("user_id", u.id);
      items = (wl ?? []).map((w) => byArea.get(w.area)).filter(Boolean) as typeof items;
    }
    if (!items.length && !alerts.length) continue;
    if (plan === "enterprise") {
      const hookOwner = u.team_owner ? (await admin.from("profiles").select("slack_webhook").eq("id", u.team_owner).single()).data?.slack_webhook : u.slack_webhook;
      if (hookOwner && !u.team_owner) await slack(hookOwner, week, items, alerts); // one post per team, from the owner
    }
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: FROM, to: u.email, ...(Date.now() < Date.parse(sevenAmLondon(week)) ? { scheduled_at: sevenAmLondon(week) } : {}), subject: items.length ? `Your Monday Brief: ${items.map((i) => i.area).join(", ")}` : `New planning filings near your saved places`, html: html(u.full_name, week, items, alerts) }),
    });
    r.ok ? sent++ : failed.push(u.id);
  }
  await admin.from("brief_sends").insert({ week, sent, failed: failed.length });
  return new Response(JSON.stringify({ sent, failed: failed.length }), { headers: { "Content-Type": "application/json" } });
});
