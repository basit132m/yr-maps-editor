/* Upgrade panels open when their upgrade is ticked.
   Progressive enhancement only: with scripting off, every panel is simply
   visible and the form behaves exactly as it always did. */
(function () {
  "use strict";

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

/* ---------------------------------------------------------------- chat

   Polling rather than a websocket: the volume is a handful of
   conversations, polling survives every proxy without reconnection logic,
   and a stale socket cannot silently swallow a message. It only runs
   while the panel is open, and backs off when the tab is hidden. */
(function () {
  "use strict";

  var root = document.querySelector("[data-chat]");
  if (!root) return;

  var panel = root.querySelector("[data-chat-panel]");
  var log = root.querySelector("[data-chat-log]");
  var form = root.querySelector("[data-chat-form]");
  var input = form.querySelector("input");
  var openButton = root.querySelector("[data-chat-open]");
  var unread = root.querySelector("[data-chat-unread]");

  var lastId = 0;
  var timer = null;
  var unseen = 0;

  root.hidden = false;

  function append(message) {
    var node = document.createElement("div");
    node.className = "bubble" + (message.sender === "admin" ? " theirs" : " mine");
    node.textContent = message.body;      // textContent, never innerHTML
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
  }

  function showUnread() {
    unread.hidden = unseen === 0;
    unread.textContent = unseen > 9 ? "9+" : String(unseen);
  }

  function poll() {
    fetch("/chat/messages?after=" + lastId, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        data.messages.forEach(function (message) {
          lastId = Math.max(lastId, message.id);
          append(message);
          if (message.sender === "admin" && panel.hidden) unseen += 1;
        });
        if (data.messages.length) showUnread();
      })
      .catch(function () { /* offline: the next tick tries again */ });
  }

  function startPolling(interval) {
    stopPolling();
    poll();
    timer = setInterval(poll, interval);
  }

  function stopPolling() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  function setOpen(open) {
    panel.hidden = !open;
    openButton.setAttribute("aria-expanded", String(open));
    if (open) {
      unseen = 0;
      showUnread();
      input.focus();
      startPolling(3000);
    } else {
      startPolling(30000);           // still notice a reply while closed
    }
  }

  openButton.addEventListener("click", function () { setOpen(panel.hidden); });
  root.querySelector("[data-chat-close]").addEventListener("click", function () {
    setOpen(false);
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var body = input.value.trim();
    if (!body) return;
    input.value = "";

    var data = new FormData();
    data.append("body", body);
    fetch("/chat/send", { method: "POST", body: data, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.error) {
          input.value = body;
          var note = document.createElement("p");
          note.className = "chat-hint";
          note.textContent = result.error;
          log.appendChild(note);
          return;
        }
        lastId = Math.max(lastId, result.message.id);
        append(result.message);
      })
      .catch(function () { input.value = body; });
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopPolling();
    else startPolling(panel.hidden ? 30000 : 3000);
  });

  startPolling(30000);
})();

/* The admin's own thread view polls the same way. */
(function () {
  "use strict";
  var log = document.querySelector("[data-admin-thread]");
  if (!log) return;

  var id = log.getAttribute("data-admin-thread");
  var lastId = 0;
  log.querySelectorAll(".bubble").forEach(function (node) {
    lastId = Math.max(lastId, Number(node.getAttribute("data-id")) || 0);
  });
  log.scrollTop = log.scrollHeight;

  setInterval(function () {
    if (document.hidden) return;
    fetch("/admin/chats/" + id + "/messages?after=" + lastId, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        data.messages.forEach(function (message) {
          lastId = Math.max(lastId, message.id);
          var node = document.createElement("div");
          node.className = "bubble" + (message.sender === "admin" ? " mine" : "");
          node.textContent = message.body;
          log.appendChild(node);
        });
        if (data.messages.length) log.scrollTop = log.scrollHeight;
      })
      .catch(function () { /* retry on the next tick */ });
  }, 4000);
})();
