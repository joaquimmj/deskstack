// Copy-to-clipboard for the connector and marketplace URLs. Labels come from data-* attributes so both languages share it.
(function () {
  var cfg = window.DESKSTACK || {};
  var box = document.querySelector("[data-connector]");
  if (box) {
    var url = cfg.connectorUrl;
    var field = box.querySelector("code");
    var btn = box.querySelector("button");
    // The "not online yet" note sits next to the box, in the same step.
    var note = box.parentNode && box.parentNode.querySelector("[data-pending]");
    if (url) {
      field.textContent = url;
      if (note) note.hidden = true;
    } else {
      if (note) note.hidden = false;
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

// Showcase tabs (WAI-ARIA tabs pattern: click, arrow keys, Home/End).
(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  if (!tabs.length) return;
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      var p = document.getElementById(t.getAttribute("aria-controls"));
      if (p) p.hidden = !on;
    });
    if (focus) tab.focus();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t, false); });
    t.addEventListener("keydown", function (e) {
      var j = { ArrowDown: i + 1, ArrowRight: i + 1, ArrowUp: i - 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault();
      select(tabs[(j + tabs.length) % tabs.length], true);
    });
  });
})();

// Reveal sections as they scroll in. Without IntersectionObserver, everything shows at once.
(function () {
  var els = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    els.forEach(function (el) { el.classList.add("in"); });
    return;
  }
  document.documentElement.classList.add("reveal-on");
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  els.forEach(function (el) { io.observe(el); });
})();
