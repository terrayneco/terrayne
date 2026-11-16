// Emails this week's Monday brief to every paying user with a watchlist.
// Called by the weekly GitHub Action: POST with header "x-cron-secret: <CRON_SECRET>", body { week: "YYYY-MM-DD" }.
// Deploy with --no-verify-jwt (protected by CRON_SECRET instead).
import { admin, SITE } from "../_shared/common.ts";

const FROM = Deno.env.get("BRIEF_FROM") ?? "Terrayne <briefings@terrayne.co.uk>";
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

function html(name: string, week: string, items: { area: string; title: string; body: string }[]) {
  const d = new Date(week + "T07:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return `<div style="background:#060d1a;padding:32px 16px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff">
<div style="max-width:620px;margin:0 auto">
<p style="letter-spacing:.2em;font-size:11px;color:#9fd0ff;text-transform:uppercase;margin:0 0 8px">Terrayne · Monday Brief · ${d}</p>
<h1 style="font-size:24px;margin:0 0 20px">Good morning${name ? ", " + esc(name.split(" ")[0]) : ""}.</h1>
${items.map((b) => `<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:18px 20px;margin:0 0 12px">
<p style="font-size:12px;color:#8c9ab3;margin:0 0 4px">${esc(b.area)}</p><h2 style="font-size:17px;margin:0 0 8px">${esc(b.title)}</h2>
<div style="font-size:14px;line-height:1.55;color:#c8d4e8">${b.body}</div></div>`).join("")}
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

Deno.serve(async (req) => {
  if (req.headers.get("x-cron-secret") !== Deno.env.get("CRON_SECRET")) return new Response("forbidden", { status: 403 });
  const { week } = await req.json();
  const { data: briefs } = await admin.from("briefs").select("area,title,body").eq("week", week);
  if (!briefs?.length) return new Response(JSON.stringify({ sent: 0, reason: "no briefs" }));
  const byArea = new Map(briefs.map((b) => [b.area, b]));
  const { data: users } = await admin.from("profiles").select("id,email,full_name,brief_email").eq("brief_email", true);
  let sent = 0;
  const failed: string[] = [];
  for (const u of users ?? []) {
    const { data: plan } = await admin.rpc("effective_plan", { uid: u.id });
    if (plan !== "pro" && plan !== "enterprise") continue; // Monday brief is Professional and up
    const { data: wl } = await admin.from("watchlist").select("area").eq("user_id", u.id);
    const items = (wl ?? []).map((w) => byArea.get(w.area)).filter(Boolean) as { area: string; title: string; body: string }[];
    if (!items.length) continue;
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: FROM, to: u.email, ...(Date.now() < Date.parse(sevenAmLondon(week)) ? { scheduled_at: sevenAmLondon(week) } : {}), subject: `Your Monday Brief: ${items.map((i) => i.area).join(", ")}`, html: html(u.full_name, week, items) }),
    });
    r.ok ? sent++ : failed.push(u.id);
  }
  await admin.from("brief_sends").insert({ week, sent, failed: failed.length });
  return new Response(JSON.stringify({ sent, failed: failed.length }), { headers: { "Content-Type": "application/json" } });
});
