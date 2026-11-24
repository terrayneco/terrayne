/* Land-use filter for the Monday Brief page (brief.html). Keep in step with supabase/functions/_shared/uses.ts. */
(function(){
var NAMES={res:"New homes",ma:"Office-to-home (Class MA)",com:"Commercial",ind:"Industrial & logistics"};
var IND=/\b(B2|B8|B1\s?\(c\)|E\(g\)\s?\(iii\))|industrial|warehous|logistic|distribution cent|data cent|depot|open storage|contractors?\W? yard/i;
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function usesOf(i){var u=[];if(/class ma/i.test(i.kind||""))u.push("ma");else if((i.units||0)>0)u.push("res");if(IND.test(i.desc||""))u.push("ind");else if((i.com||0)>=200)u.push("com");return u.length?u:["com"]}
function wanted(i,w){return usesOf(i).some(function(u){return w.indexOf(u)>-1})}
function active(w){return Array.isArray(w)&&w.length>0&&w.length<4?w:null}
function nf(n){return Number(n).toLocaleString("en-GB")}
function size(i){return[(i.units||0)>0?nf(i.units)+" home"+(i.units===1?"":"s"):"",(i.com||0)>=200?nf(i.com)+" m² commercial":""].filter(Boolean).join(" · ")}
function li(i,dec){var tag=dec?"<b style='color:"+(i.status==="Approved"?"#1fa971":"#e05252")+"'>"+esc(i.status)+"</b> · ":"";var meta=[size(i),i.kind||"",dec?"":i.status||""].filter(Boolean).join(" · ");
 return "<li style='margin:0 0 10px'>"+tag+"<b>"+esc(i.site)+"</b>: "+esc(meta)+(i.why&&!dec?"<br><span>"+esc(i.why)+"</span>":"")+"<br><span style='color:#8c9ab3'>"+esc(i.desc)+"</span><br><a href='"+esc(i.url)+"' style='color:#4c9bff'>"+esc(i.lpa||"Council")+" ref "+esc(i.ref)+" →</a></li>"}
function filterBrief(b,w){var d=b.data;if(!w||!d||!Array.isArray(d.items))return b;
 var it=d.items.filter(function(i){return wanted(i,w)}),de=(d.decided||[]).filter(function(i){return wanted(i,w)}),lo=(d.london||[]).filter(function(i){return wanted(i,w)});
 var m=(b.body||"").match(/^<p>[\s\S]*?<\/p>/),p=[m?m[0]:""];
 if(de.length)p.push("<p><b>Decided this week</b></p><ul style='padding-left:18px'>"+de.map(function(i){return li(i,true)}).join("")+"</ul>");
 if(it.length){var un=it.reduce(function(s,i){return s+Math.max(0,i.units||0)},0),co=it.reduce(function(s,i){return s+Math.max(0,i.com||0)},0);
  var pr=[un?nf(un)+" net new home"+(un===1?"":"s"):"",co?nf(co)+" m² of commercial space":""].filter(Boolean).join(" and ");
  p.push("<p><b>"+it.length+" new significant filing"+(it.length===1?"":"s")+"</b>"+(pr?", proposing "+pr:"")+"</p><ul style='padding-left:18px'>"+it.map(function(i){return li(i)}).join("")+"</ul>")}
 if(!it.length&&!de.length)p.push("<p>Nothing filed or decided here this week in the types of scheme you follow.</p>");
 p.push("<p style='font-size:12px;color:#8c9ab3'>Showing: "+w.map(function(x){return NAMES[x]}).join(", ")+".</p>");
 var bits=[it.length?it.length+" new":"",de.length?de.length+" decided":""].filter(Boolean);
 var nd={};for(var k in d)nd[k]=d[k];nd.items=it;nd.decided=de;nd.london=lo;
 return{area:b.area,title:b.title.split(" · ")[0]+(bits.length?" · "+bits.join(", "):""),body:p.join(""),data:nd}}
window.tyUses={NAMES:NAMES,usesOf:usesOf,wanted:wanted,active:active,filterBrief:filterBrief};
})();
