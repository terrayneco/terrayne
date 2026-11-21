/* Terrayne: "Download PDF" that saves an A4 PDF file straight away (html2pdf.js, MIT, self-hosted in assets/vendor).
   tyPDF(element, "File name.pdf", button). If anything fails, it falls back to the browser's print window. */
(function () {
  var SRC = "/assets/vendor/html2pdf.bundle.min.js", loading = null;
  function load() {
    if (window.html2pdf) return Promise.resolve();
    if (!loading) loading = new Promise(function (ok, no) {
      var s = document.createElement("script"); s.src = SRC; s.onload = ok; s.onerror = no; document.head.appendChild(s);
    });
    return loading;
  }
  if (!document.getElementById("pdf-css")) {
    var st = document.createElement("style"); st.id = "pdf-css";
    st.textContent = ".pdfmode .noprint{display:none!important}.pdfmode .page{box-shadow:none!important;margin:0!important;max-width:none!important;border-radius:0!important}"
      /* PDFs always use the desktop layout, even when made on a phone */
      + ".pdfcopy table{display:table!important;width:100%!important}.pdfcopy thead{display:table-header-group!important}.pdfcopy tbody{display:table-row-group!important}.pdfcopy tr{display:table-row!important;padding:0!important;border:0!important}.pdfcopy td,.pdfcopy th{display:table-cell!important;width:auto!important;margin:0!important;padding:7px 6px 7px 0!important;border-bottom:1px solid #dde3ee!important;font-size:12.5px!important}.pdfcopy td.n,.pdfcopy th.n{text-align:right!important}.pdfcopy td[data-l]:before{content:none!important}"
      + ".pdfcopy .hd{flex-direction:row!important}.pdfcopy .meta{text-align:right!important}.pdfcopy .kpis{grid-template-columns:repeat(4,1fr)!important}.pdfcopy .sig{grid-template-columns:200px 1fr 40px!important}";
    document.head.appendChild(st);
  }
  window.tyPDF = function (el, filename, btn) {
    var label = btn ? btn.textContent : "";
    function done() { document.body.classList.remove("pdfmode"); if (btn) { btn.disabled = false; btn.textContent = label; } }
    if (btn) { btn.disabled = true; btn.textContent = "Preparing PDF…"; }
    var y = window.scrollY, wrap = null, copy = null;
    return load().then(function () {
      document.body.classList.add("pdfmode");
      window.scrollTo(0, 0);
      // Render a copy at a fixed A4 width, off screen, so the PDF looks the same from a phone or a desktop.
      wrap = document.createElement("div");
      wrap.style.cssText = "position:absolute;left:0;top:0;width:700px;background:#fff;z-index:-1";
      copy = el.cloneNode(true); copy.classList.add("pdfcopy");
      copy.style.cssText += ";width:700px;max-width:none;margin:0;padding:0;box-shadow:none;border-radius:0";
      wrap.appendChild(copy); document.body.appendChild(wrap);
      return window.html2pdf().set({
        margin: [12, 12, 14, 12], filename: filename,
        image: { type: "jpeg", quality: 0.96 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff", logging: false, scrollX: 0, scrollY: 0, windowWidth: 760 },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
        pagebreak: { mode: ["css", "legacy"], avoid: ["tr", ".bh", ".kpi", ".score", ".sig", "h2", ".hd"] }
      }).from(copy).toContainer().get("container", function (c) {
        // html2pdf centres its working area on screen; pin it to the left so the capture lines up on any screen width.
        c.style.margin = "0"; c.style.left = "0"; c.style.right = "auto";
      }).save();
    }).then(function () { if (wrap) wrap.remove(); window.scrollTo(0, y); done(); },
            function () { if (wrap) wrap.remove(); window.scrollTo(0, y); done(); window.print(); });
  };
})();
