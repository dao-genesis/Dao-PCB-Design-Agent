/* panel.js — 嘉立创EDA 帧流呈现 + 全量输入转发(鼠标/滚轮/键盘)。
 * 与 bridge_server.py 配对: GET /api/frame 拉帧, POST /api/input 回传输入。
 */
(function () {
  var BASE = (window.LCEDA_BRIDGE_BASE || "");
  var img = document.getElementById("screen");
  var offline = document.getElementById("offline");
  var lastSeq = -1, misses = 0;

  function poll() {
    var x = new XMLHttpRequest();
    x.open("GET", BASE + "/api/frame?t=" + Date.now(), true);
    x.responseType = "blob";
    x.onload = function () {
      if (x.status === 200) {
        misses = 0;
        offline.style.display = "none";
        var seq = x.getResponseHeader("X-Frame-Seq");
        if (seq !== String(lastSeq)) {
          lastSeq = seq;
          var url = URL.createObjectURL(x.response);
          var old = img.src;
          img.src = url;
          if (old && old.indexOf("blob:") === 0) setTimeout(function(){ URL.revokeObjectURL(old); }, 1000);
        }
      } else {
        if (++misses > 10) offline.style.display = "flex";
      }
      setTimeout(poll, 100);
    };
    x.onerror = function () {
      if (++misses > 10) offline.style.display = "flex";
      setTimeout(poll, 500);
    };
    x.send();
  }

  function post(path, body) {
    try {
      var x = new XMLHttpRequest();
      x.open("POST", BASE + path, true);
      x.setRequestHeader("Content-Type", "application/json");
      x.send(JSON.stringify(body));
    } catch (e) {}
  }

  function norm(ev) {
    var r = img.getBoundingClientRect();
    var nx = (ev.clientX - r.left) / Math.max(1, r.width);
    var ny = (ev.clientY - r.top) / Math.max(1, r.height);
    return { nx: Math.min(1, Math.max(0, nx)), ny: Math.min(1, Math.max(0, ny)) };
  }

  function mods(ev) {
    return (ev.altKey ? 1 : 0) | (ev.ctrlKey ? 2 : 0) | (ev.metaKey ? 4 : 0) | (ev.shiftKey ? 8 : 0);
  }

  var BTN = { 0: "left", 1: "middle", 2: "right" };

  img.addEventListener("mousedown", function (ev) {
    img.focus();
    var p = norm(ev);
    post("/api/input", { kind: "mouse", type: "mousePressed", nx: p.nx, ny: p.ny,
      button: BTN[ev.button] || "left", clickCount: ev.detail || 1, modifiers: mods(ev) });
    ev.preventDefault();
  });
  img.addEventListener("mouseup", function (ev) {
    var p = norm(ev);
    post("/api/input", { kind: "mouse", type: "mouseReleased", nx: p.nx, ny: p.ny,
      button: BTN[ev.button] || "left", clickCount: ev.detail || 1, modifiers: mods(ev) });
    ev.preventDefault();
  });
  var moveT = 0;
  img.addEventListener("mousemove", function (ev) {
    var now = Date.now();
    if (now - moveT < 30) return; // 33fps 上限
    moveT = now;
    var p = norm(ev);
    post("/api/input", { kind: "mouse", type: "mouseMoved", nx: p.nx, ny: p.ny,
      button: "none", modifiers: mods(ev) });
  });
  img.addEventListener("wheel", function (ev) {
    var p = norm(ev);
    post("/api/input", { kind: "mouse", type: "mouseWheel", nx: p.nx, ny: p.ny,
      deltaX: -ev.deltaX, deltaY: -ev.deltaY, modifiers: mods(ev) });
    ev.preventDefault();
  }, { passive: false });
  img.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });

  function keyPayload(ev, type) {
    return { kind: "key", type: type, key: ev.key, code: ev.code,
      keyCode: ev.keyCode || 0, modifiers: mods(ev) };
  }
  img.addEventListener("keydown", function (ev) {
    post("/api/input", keyPayload(ev, "keyDown"));
    if (ev.key && ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey) {
      post("/api/input", { kind: "char", text: ev.key });
    } else if (ev.key === "Enter") {
      post("/api/input", { kind: "char", text: "\r" });
    }
    ev.preventDefault();
  });
  img.addEventListener("keyup", function (ev) {
    post("/api/input", keyPayload(ev, "keyUp"));
    ev.preventDefault();
  });

  img.addEventListener("dragstart", function (ev) { ev.preventDefault(); });
  poll();
})();
