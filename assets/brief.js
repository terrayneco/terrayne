/* Terrayne: "Get a free sample brief" box. Email only, no account.
   Put <div data-brief-signup data-area="Ilford"></div> on a page and load this script after assets/config.js.
   Sends to the sample-brief Edge Function, which emails this week's brief for the chosen neighbourhood. */
(function () {
  var C = window.TERRAYNE || {};
  var AREAS = [["Brent Cross", "Brent Cross & Cricklewood"], ["Canada Water", "Canada Water & Surrey Quays"], ["Isle of Dogs", "Canary Wharf & Isle of Dogs"],
    ["Croydon", "Croydon town centre"], ["Ealing", "Ealing Broadway"], ["Elephant", "Elephant & Castle"], ["Greenwich Pen.", "Greenwich Peninsula"],
    ["Hammersmith", "Hammersmith & White City"], ["Ilford", "Ilford town centre"], ["King’s Cross", "King’s Cross & St Pancras"], ["Lewisham", "Lewisham town centre"],
    ["Nine Elms", "Nine Elms & Vauxhall"], ["Old Kent Road", "Old Kent Road"], ["Stratford", "Stratford & Olympic Park"], ["Tottenham Hale", "Tottenham Hale"],
    ["Wembley", "Wembley Park"], ["Whitechapel", "Whitechapel & Aldgate"], ["Woolwich", "Woolwich"]];
  var css = ".bs{background:rgba(13,24,48,.72);border:1px solid #1c2b4d;border-radius:20px;padding:clamp(18px,3vw,26px);color:#fff;text-align:left}" +
    ".bs h3{font-size:clamp(18px,2.2vw,22px);margin:0 0 6px;letter-spacing:-.01em;line-height:1.25}.bs p.bs-sub{color:#9aa7bd;font-size:14px;line-height:1.55;margin:0 0 16px}" +
    ".bs form{display:grid;grid-template-columns:1.4fr 1fr auto;gap:10px;align-items:stretch}" +
    ".bs input[type=email],.bs select{width:100%;box-sizing:border-box;background:#081226;border:1px solid #24355a;color:#fff;border-radius:12px;padding:12px 14px;font:inherit;font-size:15px;min-height:46px}" +
    ".bs select{appearance:none;-webkit-appearance:none;background-image:linear-gradient(45deg,transparent 50%,#9aa7bd 50%),linear-gradient(135deg,#9aa7bd 50%,transparent 50%);background-position:calc(100% - 18px) 20px,calc(100% - 13px) 20px;background-size:5px 5px;background-repeat:no-repeat;padding-right:34px}" +
    ".bs input:focus,.bs select:focus{outline:2px solid #9fd0ff;outline-offset:1px}" +
    ".bs button{background:#fff;color:#060d1a;border:0;border-radius:999px;padding:0 22px;font:inherit;font-weight:600;font-size:15px;min-height:46px;cursor:pointer;white-space:nowrap}.bs button:disabled{opacity:.6;cursor:default}" +
    ".bs label.bs-up{grid-column:1/-1;display:flex;gap:9px;align-items:flex-start;color:#9aa7bd;font-size:13px;line-height:1.45;cursor:pointer}.bs label.bs-up input{margin:2px 0 0;accent-color:#9fd0ff;flex:none}" +
    ".bs .bs-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}" +
    ".bs .bs-msg{margin:12px 0 0;font-size:14px;line-height:1.5}.bs .bs-msg.ok{color:#7ee0b5}.bs .bs-msg.err{color:#ff9a9a}" +
    ".bs .bs-note{color:#6f7d96;font-size:12px;margin:10px 0 0;line-height:1.5}.bs .bs-note a{color:#9aa7bd}" +
    "@media (max-width:720px){.bs form{grid-template-columns:1fr}.bs button{width:100%}}";
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function mount(el, i) {
    var pre = el.getAttribute("data-area") || "", root = el.getAttribute("data-root") || "";
    var title = el.getAttribute("data-title") || (pre ? "Get this week’s brief for " + ((AREAS.filter(function (a) { return a[0] === pre; })[0] || [0, pre])[1]) + ", free." : "Get a free sample Monday brief.");
    var sub = el.getAttribute("data-sub") || "Pick a neighbourhood and we’ll email you this week’s brief: what was filed, what moved and why it matters. No account or card needed.";
    var id = "bs" + i;
    el.innerHTML = '<div class="bs"><h3>' + esc(title) + '</h3><p class="bs-sub">' + esc(sub) + '</p>' +
      '<form novalidate><label class="bs-hp" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>' +
      '<input type="email" name="email" required autocomplete="email" placeholder="Your work email" aria-label="Your email">' +
      '<select name="area" aria-label="Neighbourhood"><option value="">Choose a neighbourhood</option>' +
      AREAS.map(function (a) { return '<option value="' + esc(a[0]) + '"' + (a[0] === pre ? " selected" : "") + ">" + esc(a[1]) + "</option>"; }).join("") + "</select>" +
      '<button type="submit">Send my brief</button>' +
      '<label class="bs-up" for="' + id + 'u"><input type="checkbox" id="' + id + 'u" name="updates">Also send me occasional Terrayne updates (new features, new areas). You can stop them any time.</label></form>' +
      '<div class="bs-msg" role="status" aria-live="polite"></div>' +
      '<p class="bs-note">One email now, and updates only if you tick the box. See our <a href="' + root + 'privacy.html">privacy policy</a>.</p></div>';
    var f = el.querySelector("form"), m = el.querySelector(".bs-msg"), btn = el.querySelector("button");
    function say(t, ok) { m.className = "bs-msg " + (ok ? "ok" : "err"); m.textContent = t; }
    f.onsubmit = async function (e) {
      e.preventDefault();
      var em = f.email.value.trim(), ar = f.area.value;
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em)) { say("Please enter a valid email address."); f.email.focus(); return; }
      if (!ar) { say("Please choose a neighbourhood."); f.area.focus(); return; }
      if (!C.supabaseUrl || !C.supabaseAnonKey) { say("Sign-ups aren’t switched on yet. Please email hello@terrayne.co."); return; }
      btn.disabled = true; btn.textContent = "Sending…"; say("", true);
      try {
        var r = await fetch(C.supabaseUrl + "/functions/v1/sample-brief", {
          method: "POST", headers: { apikey: C.supabaseAnonKey, "Content-Type": "application/json" },
          body: JSON.stringify({ email: em, area: ar, updates: f.updates.checked, source: location.pathname, website: f.website.value })
        });
        var d = await r.json().catch(function () { return {}; });
        if (!r.ok || !d.ok) throw new Error(d.error || "Something went wrong. Please try again.");
        say(d.queued ? "You’re signed up. This week’s brief isn’t ready yet, so we’ll send it as soon as it is." : "Sent. Check your inbox in the next minute or two (and your spam folder, just in case).", true);
        f.reset(); if (pre) f.area.value = pre;
        if (window.tyTrack) window.tyTrack("brief_signup", ar);
      } catch (err) { say(err.message || "Something went wrong. Please try again."); }
      btn.disabled = false; btn.textContent = "Send my brief";
    };
  }
  function init() {
    if (!document.getElementById("bs-css")) { var s = document.createElement("style"); s.id = "bs-css"; s.textContent = css; document.head.appendChild(s); }
    Array.prototype.forEach.call(document.querySelectorAll("[data-brief-signup]"), mount);
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
