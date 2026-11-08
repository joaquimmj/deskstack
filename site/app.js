// Copy-to-clipboard for the connector and marketplace URLs. Labels come from data-* attributes so both languages share it.
(function () {
  var cfg = window.DESKSTACK || {};
  var box = document.querySelector("[data-connector]");
  if (box) {
    var url = cfg.connectorUrl;
    var field = box.querySelector("code");
    var btn = box.querySelector("button");
    var note = box.querySelector("[data-pending]");
    if (url) {
      field.textContent = url;
      note.hidden = true;
    } else {
      field.textContent = box.getAttribute("data-placeholder");
      btn.disabled = true;
    }
  }
  document.querySelectorAll("button[data-copy]").forEach(function (b) {
    b.setAttribute("aria-live", "polite");
    b.addEventListener("click", function () {
      var src = document.getElementById(b.getAttribute("data-copy"));
      var text = src ? src.textContent.trim() : "";
      if (!text || b.disabled) return;
      var label = b.textContent;
      var show = function (msg) {
        b.textContent = msg;
        setTimeout(function () { b.textContent = label; }, 2200);
      };
      var fallback = function () {
        // The clipboard API can be unavailable (http, permissions): select the text so Ctrl+C copies it.
        var r = document.createRange();
        r.selectNodeContents(src);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        show(b.getAttribute("data-fallback"));
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { show(b.getAttribute("data-done")); }, fallback);
      } else {
        fallback();
      }
    });
  });
})();
