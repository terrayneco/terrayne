// Emails Terrayne briefs and alerts. Three ways in:
//  1. Weekly GitHub Action: header "x-cron-secret: <CRON_SECRET>", body { week: "YYYY-MM-DD" } -> the Monday Brief for every paying user.
//  2. Daily GitHub Action (scripts/instant.py): x-cron-secret, body { instant: [{ place_id, items }] } -> same-day alerts for Team.
//  3. A signed-in Pro/Team user (account page), body { first: true } -> this week's brief straight away, once per account.
// Deploy with --no-verify-jwt (cron calls use CRON_SECRET; user calls are checked with their sign-in token).
import { admin, SITE, cors } from "../_shared/common.ts";

const FROM = Deno.env.get("BRIEF_FROM") ?? "Terrayne <briefings@terrayne.co>";
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

// ---- Land-use filter for the Monday Brief (keep in step with assets/uses.js and planning.html) ----
const USE_NAMES: Record<string, string> = { res: "New homes", ma: "Office-to-home (Class MA)", com: "Commercial", ind: "Industrial & logistics" };
const IND = /\b(B2|B8|B1\s?\(c\)|E\(g\)\s?\(iii\))|industrial|warehous|logistic|distribution cent|data cent|depot|open storage|contractors?\W? yard/i;
type It = { kind?: string; units?: number; com?: number; desc?: string; site?: string; lpa?: string; ref?: string; status?: string; why?: string; url?: string };
const escU = (s: string) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

function usesOf(i: It): string[] {
  const u: string[] = [];
  if (/class ma/i.test(i.kind ?? "")) u.push("ma"); else if ((i.units ?? 0) > 0) u.push("res");
  if (IND.test(i.desc ?? "")) u.push("ind"); else if ((i.com ?? 0) >= 200) u.push("com");
  return u.length ? u : ["com"];
}
const wanted = (i: It, want: string[]) => usesOf(i).some((u) => want.includes(u));
const active = (w?: string[] | null) => Array.isArray(w) && w.length > 0 && w.length < 4 ? w : null;

function size(i: It) {
  return [(i.units ?? 0) > 0 ? `${(i.units!).toLocaleString("en-GB")} home${i.units === 1 ? "" : "s"}` : "",
    (i.com ?? 0) >= 200 ? `${i.com!.toLocaleString("en-GB")} m² commercial` : ""].filter(Boolean).join(" · ");
}
function li(i: It, decided = false) {
  const tag = decided ? `<b style='color:${i.status === "Approved" ? "#1fa971" : "#e05252"}'>${escU(i.status ?? "")}</b> · ` : "";
  const meta = [size(i), i.kind ?? "", decided ? "" : i.status ?? ""].filter(Boolean).join(" · ");
  return `<li style='margin:0 0 10px'>${tag}<b>${escU(i.site ?? "")}</b>: ${escU(meta)}${i.why && !decided ? `<br><span>${escU(i.why)}</span>` : ""}<br>` +
    `<span style='color:#8c9ab3'>${escU(i.desc ?? "")}</span><br><a href='${escU(i.url ?? "")}' style='color:#4c9bff'>${escU(i.lpa || "Council")} ref ${escU(i.ref ?? "")} →</a></li>`;
}

// Returns a copy of one area's brief showing only the chosen land uses (title, body and data rebuilt).
// deno-lint-ignore no-explicit-any
function filterBrief<B extends { title: string; body: string; data?: any }>(b: B, want: string[] | null): B {
  const d = b.data;
  if (!want || !d || !Array.isArray(d.items)) return b;
  const items: It[] = d.items.filter((i: It) => wanted(i, want));
  const decided: It[] = (d.decided ?? []).filter((i: It) => wanted(i, want));
  const london: It[] = (d.london ?? []).filter((i: It) => wanted(i, want));
  const first = (b.body.match(/^<p>.*?<\/p>/s) ?? [""])[0];
  const p = [first];
  if (decided.length) p.push(`<p><b>Decided this week</b></p><ul style='padding-left:18px'>${decided.map((i) => li(i, true)).join("")}</ul>`);
  if (items.length) {
    const units = items.reduce((s, i) => s + Math.max(0, i.units ?? 0), 0), com = items.reduce((s, i) => s + Math.max(0, i.com ?? 0), 0);
    const prop = [units ? `${units.toLocaleString("en-GB")} net new home${units === 1 ? "" : "s"}` : "", com ? `${com.toLocaleString("en-GB")} m² of commercial space` : ""].filter(Boolean).join(" and ");
    p.push(`<p><b>${items.length} new significant filing${items.length === 1 ? "" : "s"}</b>${prop ? `, proposing ${prop}` : ""}</p><ul style='padding-left:18px'>${items.map((i) => li(i)).join("")}</ul>`);
  }
  if (!items.length && !decided.length) p.push(`<p>Nothing filed or decided here this week in the types of scheme you follow.</p>`);
  p.push(`<p style='font-size:12px;color:#8c9ab3'>Showing: ${want.map((w) => USE_NAMES[w]).join(", ")}.</p>`);
  const base = b.title.split(" · ")[0];
  const bits = [items.length ? `${items.length} new` : "", decided.length ? `${decided.length} decided` : ""].filter(Boolean);
  return { ...b, title: base + (bits.length ? " · " + bits.join(", ") : ""), body: p.join(""), data: { ...d, items, decided, london } };
}
// ---- end land-use filter ----

type Item = { site: string; lpa: string; ref: string; units: number; com: number; kind: string; status: string; why?: string; url?: string; desc?: string };
type Watch = { n: string; f: string; s: number; move: number; why: string };
type Scout = { n: string; f: string; s: number; hd?: number };
type BriefData = { name?: string; move?: number; items?: Item[]; decided?: Item[]; london?: Item[]; watch?: Watch | null; scout?: Scout[] };
type Brief = { area: string; title: string; body: string; data?: BriefData | null };
const plural = (n: number, w: string) => `${n.toLocaleString("en-GB")} ${w}${n === 1 ? "" : "s"}`;

// One-line summary across the reader's neighbourhoods (only for briefs built since the data fields were added).
function headline(items: Brief[]) {
  const ds = items.map((b) => b.data).filter((d): d is BriefData => !!d && Array.isArray(d.items));
  if (!ds.length) return "";
  const n = ds.reduce((s, d) => s + (d.items?.length ?? 0), 0);
  const homes = ds.reduce((s, d) => s + (d.items ?? []).reduce((t, i) => t + Math.max(0, i.units || 0), 0), 0);
  const dec = ds.flatMap((d) => d.decided ?? []);
  const ok = dec.filter((i) => i.status === "Approved").length;
  const mv = ds.filter((d) => typeof d.move === "number").sort((a, b) => Math.abs(b.move!) - Math.abs(a.move!))[0];
  const where = ds.length === 1 ? "your neighbourhood" : `your ${ds.length} neighbourhoods`;
  const what = n || dec.length
    ? `This week across ${where}: ${n ? plural(n, "new significant filing") + (homes ? ` (${plural(homes, "home")})` : "") : "no new significant filings"}` +
      (dec.length ? ` and ${plural(dec.length, "decision")} (${ok} approved, ${dec.length - ok} refused)` : "") + "."
    : `A quiet week across ${where}: no new significant filings or decisions.`;
  const big = mv && mv.move ? ` Biggest mover: ${mv.name}, ${mv.move > 0 ? "up" : "down"} ${Math.abs(mv.move)} pts.` : "";
  return what + big;
}

function watchHtml(items: Brief[]) {
  const d = items.map((b) => b.data).find((x) => x && x.watch);
  if (!d || !d.watch) return "";
  const w = d.watch, sc = d.scout ?? [];
  const head = (hd?: number) => hd == null ? "" : hd >= 99 ? "prices among the lowest in London" : `cheaper than ${hd}% of London`;
  return `<h2 style="font-size:17px;margin:22px 0 10px">Location to watch</h2><div style="background:linear-gradient(135deg,#13284d,#0d1830);border:1px solid #2f4677;border-radius:16px;padding:16px 18px;margin:0 0 12px">` +
    `<p style="margin:0 0 6px;font-size:16px;color:#fff"><b>${esc(w.f)}</b> · ${w.s}/100</p><p style="margin:0;font-size:14px;line-height:1.55;color:#c8d4e8">${esc(w.why)}</p>` +
    (sc.length ? `<p style="margin:14px 0 6px;font-size:13px;color:#9fd0ff;letter-spacing:.06em">ALSO WORTH INVESTIGATING · MOMENTUM WITH PRICE HEADROOM</p><ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.55;color:#c8d4e8">` +
      sc.map((x) => `<li><b style="color:#fff">${esc(x.f)}</b>: ${x.s}/100, ${head(x.hd)}</li>`).join("") + `</ul>` : "") +
    `<p style="margin:12px 0 0;font-size:12px;color:#8c9ab3">A starting point for your own research, not a recommendation. <a href="${SITE}/account.html#index" style="color:#9fd0ff">Every score in your account</a></p></div>`;
}

function londonHtml(items: Brief[]) {
  const top = items.map((b) => b.data?.london).find((l) => l && l.length) ?? [];
  if (!top.length) return "";
  return `<h2 style="font-size:17px;margin:22px 0 10px">Biggest new schemes in London this week</h2><div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:16px 18px;margin:0 0 12px"><ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.55;color:#c8d4e8">` +
    top.map((i) => `<li style="margin-bottom:10px"><b style="color:#fff">${esc(i.site)}</b> (${esc(i.lpa || "")}): ${[i.units > 0 ? plural(i.units, "home") : "", i.com >= 200 ? `${i.com.toLocaleString("en-GB")} m² commercial` : "", esc(i.kind)].filter(Boolean).join(" · ")}` +
      (i.why ? `<br>${esc(i.why)}` : "") + (i.url ? `<br><a href="${esc(i.url)}" style="color:#5aa9ff">Ref ${esc(i.ref)} →</a>` : "") + `</li>`).join("") + `</ul></div>`;
}

function html(name: string, week: string, items: Brief[], alerts: Alert[] = [], intro = "") {
  const hl = headline(items);
  const d = new Date(week + "T07:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return `<div style="background:#060d1a;padding:32px 16px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff">
<div style="max-width:620px;margin:0 auto">
<img src="https://terrayne.co/assets/email-logo.png" width="180" height="60" alt="Terrayne" style="display:block;border:0;color:#ffffff;font-size:18px;margin:0 0 14px">
<p style="letter-spacing:.2em;font-size:11px;color:#9fd0ff;text-transform:uppercase;margin:0 0 8px">Monday Brief · ${d}</p>
<h1 style="font-size:24px;margin:0 0 ${hl ? 10 : 20}px">${intro ? "Hello" : "Good morning"}${name ? ", " + esc(name.split(" ")[0]) : ""}.</h1>
${intro ? `<p style="font-size:15px;line-height:1.55;color:#9fd0ff;margin:0 0 12px">${esc(intro)}</p>` : ""}
${hl ? `<p style="font-size:15px;line-height:1.55;color:#c8d4e8;margin:0 0 20px">${esc(hl)}</p>` : ""}${items.map((b) => `<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:18px 20px;margin:0 0 12px">
<p style="font-size:12px;color:#8c9ab3;margin:0 0 4px">${esc(b.area)}</p><h2 style="font-size:17px;margin:0 0 8px">${esc(b.title)}</h2>
<div style="font-size:14px;line-height:1.55;color:#c8d4e8">${b.body}</div></div>`).join("")}
${alertsHtml(alerts)}
${watchHtml(items)}
${londonHtml(items)}
<p style="margin:22px 0 0"><a href="${SITE}/brief.html?week=${week}&pdf=1" style="display:inline-block;padding:10px 18px;border-radius:999px;background:#ffffff;color:#060d1a;font-weight:600;font-size:14px;text-decoration:none">Download this brief as a PDF</a></p>
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

async function alertsFor(uid: string, week: string, want: string[] | null = null): Promise<Alert[]> {
  const { data: me } = await admin.from("profiles").select("team_owner").eq("id", uid).single();
  const owners = [uid, ...(me?.team_owner ? [me.team_owner] : [])];
  const { data: places } = await admin.from("saved_places").select("id,label,postcode,radius_m").in("owner", owners);
  if (!places?.length) return [];
  const { data: rows } = await admin.from("alerts").select("place_id,items").eq("week", week).in("place_id", places.map((p) => p.id));
  return (rows ?? []).map((r) => {
    const p = places.find((x) => x.id === r.place_id)!;
    const items = (r.items as Alert["items"]).filter((i) => !want || wanted(i, want));
    return { label: p.label, postcode: p.postcode, radius_m: p.radius_m, items };
  }).filter((a) => a.items.length);
}

async function send(to: string, subject: string, body: string, at?: string) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to, ...(at ? { scheduled_at: at } : {}), subject, html: body }),
  });
  return r.ok;
}

type Instant = Item & { alert: "new" | "decided"; dist?: number };
function instantHtml(name: string, groups: { label: string; radius_m: number; items: Instant[] }[]) {
  const li = (i: Instant) => {
    const tag = i.alert === "decided" ? `<b style="color:${i.status === "Approved" ? "#1fa971" : "#e05252"}">${esc(i.status)}</b>` : `<b style="color:#9fd0ff">New filing</b>`;
    const size = [i.units > 0 ? plural(i.units, "home") : "", i.com >= 200 ? `${i.com.toLocaleString("en-GB")} m² commercial` : "", esc(i.kind)].filter(Boolean).join(" · ");
    return `<li style="margin-bottom:12px">${tag} · <b style="color:#fff">${esc(i.site)}</b>: ${size}${typeof i.dist === "number" ? ` · ${i.dist.toLocaleString("en-GB")} m away` : ""}` +
      (i.why ? `<br>${esc(i.why)}` : "") + (i.desc ? `<br><span style="color:#8c9ab3">${esc(i.desc)}</span>` : "") +
      (i.url ? `<br><a href="${esc(i.url)}" style="color:#4c9bff">${esc(i.lpa || "Council")} ref ${esc(i.ref)} →</a>` : "") + `</li>`;
  };
  return `<div style="background:#060d1a;padding:32px 16px;font-family:-apple-system,Helvetica,Arial,sans-serif;color:#fff"><div style="max-width:620px;margin:0 auto">
<img src="https://terrayne.co/assets/email-logo.png" width="180" height="60" alt="Terrayne" style="display:block;border:0;color:#ffffff;font-size:18px;margin:0 0 14px">
<p style="letter-spacing:.2em;font-size:11px;color:#9fd0ff;text-transform:uppercase;margin:0 0 8px">Same-day alert</p>
<h1 style="font-size:22px;margin:0 0 16px">${name ? esc(name.split(" ")[0]) + ", s" : "S"}omething big just landed near your saved place${groups.length > 1 ? "s" : ""}.</h1>
${groups.map((g) => `<div style="background:#0d1830;border:1px solid #1c2b4d;border-radius:16px;padding:16px 18px;margin:0 0 12px"><p style="font-size:12px;color:#8c9ab3;margin:0 0 8px">${esc(g.label)} · within ${g.radius_m.toLocaleString("en-GB")} m</p><ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.55;color:#c8d4e8">${g.items.map(li).join("")}</ul></div>`).join("")}
<p style="font-size:13px;color:#8c9ab3;margin:20px 0 0"><a href="${SITE}/account.html#places" style="color:#9fd0ff">Your saved places</a> · <a href="${SITE}/account.html#profile" style="color:#9fd0ff">Turn off same-day alerts</a></p>
<p style="font-size:11px;color:#52617f">Built from the GLA Planning London Datahub. Statuses can change; check the council record by reference.</p></div></div>`;
}

async function instant(list: { place_id: number; items: Instant[] }[]) {
  const ids = list.map((x) => x.place_id);
  const { data: places } = await admin.from("saved_places").select("id,owner,label,postcode,radius_m").in("id", ids);
  const byUser = new Map<string, { label: string; radius_m: number; items: Instant[] }[]>();
  const users = new Map<string, { email: string; full_name: string }>();
  for (const x of list) {
    const p = (places ?? []).find((q) => q.id === x.place_id);
    if (!p) continue;
    const { data: team } = await admin.from("profiles").select("id,email,full_name,instant_email").or(`id.eq.${p.owner},team_owner.eq.${p.owner}`);
    for (const u of team ?? []) {
      if (u.instant_email === false || !u.email) continue;
      const { data: plan } = await admin.rpc("effective_plan", { uid: u.id });
      if (plan !== "enterprise") continue;
      users.set(u.id, { email: u.email, full_name: u.full_name });
      const g = byUser.get(u.id) ?? [];
      g.push({ label: p.label ? `${p.label} (${p.postcode})` : p.postcode, radius_m: p.radius_m, items: x.items });
      byUser.set(u.id, g);
    }
  }
  let sent = 0;
  for (const [id, groups] of byUser) {
    const u = users.get(id)!;
    const all = groups.flatMap((g) => g.items);
    const top = [...all].sort((a, b) => (b.units || 0) - (a.units || 0) || (b.com || 0) - (a.com || 0))[0];
    const what = top.alert === "decided" ? `${top.status.toLowerCase()}` : "filed";
    const size = top.units > 0 ? plural(top.units, "home") : top.com >= 200 ? `${top.com.toLocaleString("en-GB")} m²` : top.kind.toLowerCase();
    const subject = `Terrayne alert: ${size} ${what} near ${groups[0].label}` + (all.length > 1 ? ` (+${all.length - 1} more)` : "");
    if (await send(u.email, subject, instantHtml(u.full_name, groups))) sent++;
  }
  return { sent, recipients: byUser.size };
}

async function firstBrief(req: Request) {
  const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: who } = await admin.auth.getUser(jwt);
  const uid = who?.user?.id;
  if (!uid) return { sent: false, reason: "signin" };
  const { data: plan } = await admin.rpc("effective_plan", { uid });
  if (plan !== "pro" && plan !== "enterprise") return { sent: false, reason: "plan" };
  let { data: prof, error: pe } = await admin.from("profiles").select("email,full_name,brief_email,brief_uses").eq("id", uid).single();
  if (pe) prof = (await admin.from("profiles").select("email,full_name,brief_email").eq("id", uid).single()).data as typeof prof;
  if (!prof?.email || prof.brief_email === false) return { sent: false, reason: "email_off" };
  const { data: wl } = await admin.from("watchlist").select("area").eq("user_id", uid);
  const areas = (wl ?? []).map((w) => w.area);
  if (!areas.length) return { sent: false, reason: "watchlist" };
  const { data: last } = await admin.from("briefs").select("week").order("week", { ascending: false }).limit(1);
  const week = last?.[0]?.week;
  if (!week) return { sent: false, reason: "none" };
  const { error: dup } = await admin.from("first_briefs").insert({ user_id: uid, week });
  if (dup) return { sent: false, reason: "already" };
  const { data: rows } = await admin.from("briefs").select("area,title,body,data").eq("week", week).in("area", areas);
  const items = ((rows ?? []) as Brief[]).map((b) => filterBrief(b, active(prof.brief_uses)));
  const ok = items.length && await send(prof.email, `Your first Monday Brief: ${items.map((i) => i.area).join(", ")}`,
    html(prof.full_name, week, items, [], "Welcome to Terrayne. Here’s this week’s brief for your neighbourhoods so you don’t have to wait. The next one arrives on Monday by 7am UK time."));
  if (!ok) { await admin.from("first_briefs").delete().eq("user_id", uid); return { sent: false, reason: "send" }; }
  return { sent: true, week };
}

const json = (b: unknown, h: Record<string, string> = {}) => new Response(JSON.stringify(b), { headers: { "Content-Type": "application/json", ...h } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const isCron = req.headers.get("x-cron-secret") === Deno.env.get("CRON_SECRET");
  const body = await req.json().catch(() => ({}));
  if (!isCron) {
    if (body.first) return json(await firstBrief(req), cors);
    return new Response("forbidden", { status: 403, headers: cors });
  }
  if (Array.isArray(body.instant)) return json(await instant(body.instant));
  const { week } = body;
  const { data: briefs } = await admin.from("briefs").select("area,title,body,data").eq("week", week);
  if (!briefs?.length) return new Response(JSON.stringify({ sent: 0, reason: "no briefs" }));
  const byArea = new Map(briefs.map((b) => [b.area, b]));
  // If the brief_uses column hasn't been added yet (supabase/2026-11-uses.sql), send everyone everything rather than nothing.
  let { data: users, error: ue } = await admin.from("profiles").select("id,email,full_name,brief_email,brief_uses,slack_webhook,team_owner").eq("brief_email", true);
  if (ue) users = (await admin.from("profiles").select("id,email,full_name,brief_email,slack_webhook,team_owner").eq("brief_email", true)).data as typeof users;
  let sent = 0;
  const failed: string[] = [];
  for (const u of users ?? []) {
    const { data: plan } = await admin.rpc("effective_plan", { uid: u.id });
    if (plan === "free" || !plan) continue;
    const want = active(u.brief_uses);                         // Land uses this reader follows (null = all)
    const alerts = await alertsFor(u.id, week, want);        // Any paid plan: alerts near saved places
    let items: Brief[] = [];
    if (plan === "pro" || plan === "enterprise") {           // Monday Brief is Pro and Team
      const { data: wl } = await admin.from("watchlist").select("area").eq("user_id", u.id);
      items = ((wl ?? []).map((w) => byArea.get(w.area)).filter(Boolean) as typeof items).map((b) => filterBrief(b, want));
    }
    if (!items.length && !alerts.length) continue;
    if (plan === "enterprise") {
      const hookOwner = u.team_owner ? (await admin.from("profiles").select("slack_webhook").eq("id", u.team_owner).single()).data?.slack_webhook : u.slack_webhook;
      if (hookOwner && !u.team_owner) await slack(hookOwner, week, items, alerts); // one post per team, from the owner
    }
    const ok = await send(u.email, items.length ? `Your Monday Brief: ${items.map((i) => i.area).join(", ")}` : `New planning filings near your saved places`,
      html(u.full_name, week, items, alerts), Date.now() < Date.parse(sevenAmLondon(week)) ? sevenAmLondon(week) : undefined);
    ok ? sent++ : failed.push(u.id);
  }
  await admin.from("brief_sends").insert({ week, sent, failed: failed.length });
  return new Response(JSON.stringify({ sent, failed: failed.length }), { headers: { "Content-Type": "application/json" } });
});
