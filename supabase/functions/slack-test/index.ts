// POST -> posts a test message to the signed-in Team owner's Slack webhook.
import { cors, json, currentUser, admin } from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const me = await currentUser(req);
  if (!me) return json({ error: "Please sign in first." }, 401);
  const { data: plan } = await admin.rpc("effective_plan", { uid: me.profile.id });
  if (plan !== "enterprise") return json({ error: "Slack delivery is part of Team." }, 403);
  const hook = me.profile.slack_webhook || "";
  if (!/^https:\/\/hooks\.slack\.com\/services\//.test(hook)) return json({ error: "Add a Slack incoming-webhook URL first." }, 400);
  const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: "✅ Terrayne is connected. Your Monday brief will arrive here at 7am." }) });
  return r.ok ? json({ ok: true }) : json({ error: "Slack rejected the message. Check the webhook URL." }, 400);
});
