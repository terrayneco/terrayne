// POST {email} -> an Enterprise owner invites a colleague. Saves the invite and emails them.
// New people are linked automatically when they sign up with that email; people who already
// have an account accept the invite from their own account page (nobody is added without consent).
import { cors, json, currentUser, admin, SITE } from "../_shared/common.ts";

const FROM = Deno.env.get("BRIEF_FROM") ?? "Terrayne <briefings@terrayne.co>";
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  const { email: raw } = await req.json().catch(() => ({}));
  const email = String(raw ?? "").trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200) return json({ error: "Please enter a valid email address." }, 400);
  if (email === (me.profile.email ?? "").toLowerCase()) return json({ error: "That’s your own email." }, 400);

  const { data: plan } = await admin.rpc("effective_plan", { uid: me.profile.id });
  if (plan !== "enterprise" || me.profile.team_owner) return json({ error: "Only Enterprise account owners can invite colleagues." }, 403);

  const { data: existing } = await admin.from("profiles").select("id,team_owner").ilike("email", email).maybeSingle();
  if (existing?.team_owner === me.profile.id) return json({ error: "They’re already in your team." }, 400);

  // The database checks the 5-seat limit and the Enterprise plan again here.
  const { error } = await admin.from("team_invites").insert({ owner: me.profile.id, email });
  if (error) {
    if (error.code === "23505") return json({ error: "You’ve already invited that email." }, 400);
    return json({ error: error.message.replace(/^.*?: /, "") }, 400);
  }

  const who = esc(me.profile.full_name || me.profile.email);
  const org = me.profile.company ? ` at ${esc(me.profile.company)}` : "";
  const link = existing ? `${SITE}/account.html` : `${SITE}/account.html?signup&email=${encodeURIComponent(email)}`;
  const action = existing
    ? "Sign in to Terrayne and accept the invitation at the top of your account page."
    : `Create your free account with <b>${esc(email)}</b> and you’ll join the team straight away.`;
  const html = `<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:520px;margin:0 auto;color:#0a1223">
<div style="background:#060d1a;border-radius:14px;padding:18px 0;text-align:center;margin:0 0 20px"><img src="https://terrayne.co/assets/email-logo.png" width="210" height="70" alt="Terrayne" style="display:inline-block;border:0;color:#ffffff;font-size:18px"></div>
<h2 style="margin:8px 0 12px">${who}${org} has invited you to their Terrayne team</h2>
<p style="line-height:1.6">Terrayne is property intelligence for London: what’s being planned around any site, how fast each neighbourhood is changing, and a brief every Monday. As part of the team you get full Enterprise access at no cost to you.</p>
<p style="line-height:1.6">${action}</p>
<p><a href="${link}" style="display:inline-block;background:#0a1223;color:#fff;padding:12px 22px;border-radius:99px;text-decoration:none">${existing ? "Accept the invitation" : "Join the team"}</a></p>
<p style="font-size:12px;color:#6b7891;line-height:1.5">If you weren’t expecting this, you can ignore it: nothing happens unless you sign in or create an account.</p></div>`;

  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to: email, reply_to: me.profile.email, subject: `${me.profile.full_name || "A colleague"} invited you to Terrayne`, html }),
  });
  return json({ ok: true, emailed: r.ok, existing: !!existing });
});
