/* Upgrade panels open when their upgrade is ticked.
   Progressive enhancement only: with scripting off, every panel is simply
   visible and the form behaves exactly as it always did. */
(function () {
  "use strict";

  /* The theme itself is applied by an inline script in the head so the page
     never flashes; this only handles the button. */
  var root = document.documentElement;
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "light" ? "dark" : "light";
      root.dataset.theme = next;
      try { localStorage.setItem("yrme-theme", next); } catch (e) { /* ignore */ }
    });
  }

  var form = document.querySelector("form[action='/apply']");
  if (!form) return;

  var panels = Array.prototype.slice.call(form.querySelectorAll("[data-mod]"));
  var counter = form.querySelector("[data-picked]");

  function sync(panel) {
    var toggle = panel.querySelector("[data-mod-toggle]");
    panel.classList.toggle("is-open", toggle.checked);
  }

  function count() {
    if (!counter) return;
    var n = panels.filter(function (panel) {
      return panel.querySelector("[data-mod-toggle]").checked;
    }).length;
    counter.textContent = n === 0
      ? "No upgrades selected yet"
      : n + (n === 1 ? " upgrade selected" : " upgrades selected");
    counter.classList.toggle("picked-none", n === 0);
  }

  panels.forEach(function (panel) {
    var toggle = panel.querySelector("[data-mod-toggle]");
    toggle.addEventListener("change", function () {
      sync(panel);
      count();
      // Opening a panel below the fold is useless if it stays off screen.
      if (toggle.checked) {
        var box = panel.getBoundingClientRect();
        if (box.bottom > window.innerHeight) {
          panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      }
    });
    sync(panel);
  });

  count();
})();
