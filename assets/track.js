/* Terrayne: anonymous step counts (checked a postcode, clicked Start free, started checkout...).
   No cookies, no storage, no names or emails: each event is just the action, the page, a short detail
   and the website the visitor came from. Counts show on admin.html. Page views come from Cloudflare. */
(function () {
  var C = window.TERRAYNE || {};
  function refHost() {
    try { var h = document.referrer ? new URL(document.referrer).hostname : ""; return h === location.hostname ? "" : h.replace(/^www\./, ""); }
    catch (e) { return ""; }
  }
  var REF = refHost(), sent = {};
  window.tyTrack = function (name, detail, once) {
    try {
      if (!C.supabaseUrl || !C.supabaseAnonKey || !/^[a-z_]{2,40}$/.test(name)) return;
      if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname) && !window.TY_TRACK_LOCAL) return;
      var key = name + "|" + (detail || "");
      if (once && sent[key]) return;
      sent[key] = 1;
      fetch(C.supabaseUrl + "/rest/v1/events", {
        method: "POST", keepalive: true,
        headers: { apikey: C.supabaseAnonKey, "Content-Type": "application/json", Prefer: "return=minimal" },
        body: JSON.stringify({ name: name, page: location.pathname.slice(0, 80), detail: String(detail || "").slice(0, 80), ref: REF.slice(0, 80) })
      }).catch(function () {});
    } catch (e) {}
  };
  // Clicks on the main calls to action, wherever they are on the site.
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a,button") : null;
    if (!a) return;
    var where = (a.closest("section[id],nav,footer") || {}).id || (a.closest("nav") ? "nav" : "");
    if (a.dataset.ev) { window.tyTrack(a.dataset.ev, a.dataset.evd || where); return; }
    var h = a.getAttribute("href") || "";
    var plan = (h.match(/[?&]plan=(pro|enterprise)/) || [])[1];
    if (plan) window.tyTrack("plan_click", plan + (where ? " · " + where : ""));
    else if (/account\.html\?signup/.test(h)) window.tyTrack("signup_click", where);
    else if (/report\.html/.test(h) && !/sample/.test(h)) window.tyTrack("report_click", where);
  }, true);
})();
