// Land-use filter for the Monday Brief. Keep in step with assets/uses.js (brief.html) and planning.html.
export const USE_NAMES: Record<string, string> = { res: "New homes", ma: "Office-to-home (Class MA)", com: "Commercial", ind: "Industrial & logistics" };
const IND = /\b(B2|B8|B1\s?\(c\)|E\(g\)\s?\(iii\))|industrial|warehous|logistic|distribution cent|data cent|depot|open storage|contractors?\W? yard/i;
type It = { kind?: string; units?: number; com?: number; desc?: string; site?: string; lpa?: string; ref?: string; status?: string; why?: string; url?: string };
const esc = (s: string) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

export function usesOf(i: It): string[] {
  const u: string[] = [];
  if (/class ma/i.test(i.kind ?? "")) u.push("ma"); else if ((i.units ?? 0) > 0) u.push("res");
  if (IND.test(i.desc ?? "")) u.push("ind"); else if ((i.com ?? 0) >= 200) u.push("com");
  return u.length ? u : ["com"];
}
export const wanted = (i: It, want: string[]) => usesOf(i).some((u) => want.includes(u));
export const active = (w?: string[] | null) => Array.isArray(w) && w.length > 0 && w.length < 4 ? w : null;

function size(i: It) {
  return [(i.units ?? 0) > 0 ? `${(i.units!).toLocaleString("en-GB")} home${i.units === 1 ? "" : "s"}` : "",
    (i.com ?? 0) >= 200 ? `${i.com!.toLocaleString("en-GB")} m² commercial` : ""].filter(Boolean).join(" · ");
}
function li(i: It, decided = false) {
  const tag = decided ? `<b style='color:${i.status === "Approved" ? "#1fa971" : "#e05252"}'>${esc(i.status ?? "")}</b> · ` : "";
  const meta = [size(i), i.kind ?? "", decided ? "" : i.status ?? ""].filter(Boolean).join(" · ");
  return `<li style='margin:0 0 10px'>${tag}<b>${esc(i.site ?? "")}</b>: ${esc(meta)}${i.why && !decided ? `<br><span>${esc(i.why)}</span>` : ""}<br>` +
    `<span style='color:#8c9ab3'>${esc(i.desc ?? "")}</span><br><a href='${esc(i.url ?? "")}' style='color:#4c9bff'>${esc(i.lpa || "Council")} ref ${esc(i.ref ?? "")} →</a></li>`;
}

// Returns a copy of one area's brief showing only the chosen land uses (title, body and data rebuilt).
// deno-lint-ignore no-explicit-any
export function filterBrief<B extends { title: string; body: string; data?: any }>(b: B, want: string[] | null): B {
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
