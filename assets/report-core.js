/* Terrayne postcode report core: shared by report.html (PDF reports, IC memos, catchments). */
(function () {
  var CITIES = {
    london: { box: [51.28, 51.70, -0.52, 0.34], dir: "data/", name: "London", hh: 2.47, hhLabel: "London’s average household size of 2.47" },
    manchester: { box: [53.33, 53.70, -2.75, -1.90], dir: "data/manchester/", name: "Greater Manchester", hh: 2.36, hhLabel: "England’s average household size of 2.36" }
  };
  var KIND = { ma: "Office/shop to homes (Class MA)", major: "Major scheme", res: "New homes", com: "Commercial space", bf: "Brownfield register site" };
  var cache = {}, tiles = {};
  function km(a, b, c, d) { return Math.hypot((d - b) * 111.32 * Math.cos((a + c) / 2 * Math.PI / 180), (c - a) * 110.57); }
  function tile(lat, lon) { var n = 8192; return [Math.floor((lon + 180) / 360 * n), Math.floor((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n)]; }
  async function J(u) { var r = await fetch(u, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return r.json(); }
  function cityOf(lat, lon) { for (var k in CITIES) { var b = CITIES[k].box; if (lat > b[0] && lat < b[1] && lon > b[2] && lon < b[3]) return k; } return null; }
  function normPC(pc) { return String(pc || "").trim().toUpperCase().replace(/\s+/g, " "); }
  async function geo(pc) {
    var r = await fetch("https://api.postcodes.io/postcodes/" + encodeURIComponent(pc));
    if (!r.ok) return null;
    var d = (await r.json()).result;
    return { lat: d.latitude, lon: d.longitude, postcode: d.postcode, ward: d.admin_ward, district: d.admin_district };
  }
  async function pts(city, x, y) {
    var k = city + ":" + x + "_" + y;
    if (!(k in cache)) { try { cache[k] = await J(CITIES[city].dir + "pts/" + x + "_" + y + ".json"); } catch (e) { cache[k] = []; } }
    return cache[k];
  }
  /* Build everything a report needs for a postcode and radius (km). */
  async function build(pc, R) {
    pc = normPC(pc);
    var g = await geo(pc);
    if (!g) return { error: "We couldn’t find that postcode." };
    var city = cityOf(g.lat, g.lon);
    if (!city) return { error: "Terrayne covers Greater London (and Greater Manchester in experimental beta)." };
    if (!tiles[city]) tiles[city] = await J(CITIES[city].dir + "tiles.json");
    var T = tiles[city];
    var dLat = R / 110.57, dLon = R / (111.32 * Math.cos(g.lat * Math.PI / 180)), a = tile(g.lat + dLat, g.lon - dLon), b = tile(g.lat - dLat, g.lon + dLon), all = [];
    for (var x = a[0]; x <= b[0]; x++) for (var y = a[1]; y <= b[1]; y++) all = all.concat(await pts(city, x, y));
    var near = all.map(function (r) { return { r: r, d: km(g.lat, g.lon, r[0], r[1]) }; })
      .filter(function (o) { return o.d <= R && o.r[5] !== "Refused" && o.r[5] !== "Withdrawn"; })
      .sort(function (p, q) { return (q.r[2] - p.r[2]) || (q.r[3] - p.r[3]); });
    var s = { homes: 0, ma: 0, com: 0, major: 0, approved: 0, pending: 0 };
    near.forEach(function (o) {
      var r = o.r; s.homes += Math.max(r[2], 0); s.com += r[3];
      if (r[4] === "ma") s.ma += Math.max(r[2], 0);
      if (r[4] === "major") s.major++;
      if (r[5] === "Approved" || r[5] === "Started" || r[5] === "Has permission") s.approved += Math.max(r[2], 0); else s.pending += Math.max(r[2], 0);
    });
    s.residents = Math.round(s.homes * CITIES[city].hh);
    var t = tile(g.lat, g.lon), ts = T.tiles["13/" + t[0] + "/" + t[1]] || null;
    var nearest = (T.areas || []).map(function (a) { return { a: a, d: km(g.lat, g.lon, a.lat, a.lon) }; }).sort(function (p, q) { return p.d - q.d; })[0];
    return { pc: g.postcode, g: g, city: city, cityInfo: CITIES[city], R: R, T: T, ts: ts, near: near, stats: s, nearest: nearest, generated: T.generated, KIND: KIND };
  }
  function verdict(s) { return s >= 80 ? "Changing fast" : s >= 65 ? "Changing" : s >= 50 ? "Steady" : "Quiet"; }
  window.TerrayneReport = { build: build, verdict: verdict, normPC: normPC, KIND: KIND, CITIES: CITIES };
})();
