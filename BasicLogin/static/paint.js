/* Paint tools for the shop pages.
   Tools: pencil (grainy), pen (smooth), bucket, magnifier, eraser, trash.
   A transparent canvas (#paintLayer) covers the whole page; drawings live on it. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  var layer = $('paintLayer');
  if (!layer) return;
  var ctx = layer.getContext('2d', { willReadFrequently: true });

  var lens = $('lens'), lensWorld = $('lensWorld'), lensCanvas = $('lensCanvas');
  var lctx = lensCanvas.getContext('2d');
  var ring = $('eraserRing');
  var zoomEl = $('zoom'), zoomVal = $('zoomVal');
  var eraseEl = $('eraseSize'), eraseVal = $('eraseVal');
  var toolName = $('toolName'), curColor = $('curColor');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('#toolbox [data-tool]'));

  var LENS_CX = 110, LENS_CY = 110, LENS_R = 88;     // must match magnifier.png / paint.css
  var PENCIL_R = 5, PEN_W = 4;
  var NAMES = { pencil: 'Pencil', pen: 'Pen', bucket: 'Fill With Color', magnifier: 'Magnifier', eraser: 'Eraser' };

  var color = '#000000', tool = null, drawing = false, last = null, pts = [];
  var fills = new Map();                              // element -> original style attr (for trash)
  var KEY = 'paintLayer:' + location.pathname;
  var lastClient = null, worldDirty = true, worldBuiltAt = 0, saveTimer = null;

  /* ---------------------------------------------------------- canvas size */
  function fit() {
    var de = document.documentElement;
    var w = Math.max(de.scrollWidth, window.innerWidth, layer.width);
    var h = Math.max(de.scrollHeight, window.innerHeight, layer.height);
    if (w === layer.width && h === layer.height) return;
    var tmp = document.createElement('canvas');
    tmp.width = layer.width; tmp.height = layer.height;
    tmp.getContext('2d').drawImage(layer, 0, 0);
    layer.width = w; layer.height = h;
    ctx.drawImage(tmp, 0, 0);
  }

  /* ----------------------------------------------------------- persistence */
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      try { sessionStorage.setItem(KEY, layer.toDataURL()); } catch (e) { /* too big / blocked */ }
    }, 400);
  }
  function restore() {
    try {
      var s = sessionStorage.getItem(KEY);
      if (!s) return;
      var img = new Image();
      img.onload = function () { fit(); ctx.drawImage(img, 0, 0); };
      img.src = s;
    } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------- drawing */
  function grain(x0, y0, x1, y1) {                    // pencil: scattered 1-2px specks
    var steps = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / 2));
    ctx.fillStyle = color;
    for (var i = 0; i <= steps; i++) {
      var x = x0 + (x1 - x0) * i / steps, y = y0 + (y1 - y0) * i / steps;
      for (var k = 0; k < 9; k++) {
        var a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * PENCIL_R;
        ctx.globalAlpha = 0.3 + Math.random() * 0.65;
        ctx.fillRect(Math.round(x + Math.cos(a) * r), Math.round(y + Math.sin(a) * r),
                     Math.random() < 0.25 ? 2 : 1, 1);
      }
    }
    ctx.globalAlpha = 1;
  }

  function penStyle() {
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.lineWidth = PEN_W; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  }
  function penDot(x, y) {
    penStyle(); ctx.beginPath(); ctx.arc(x, y, PEN_W / 2, 0, Math.PI * 2); ctx.fill();
  }
  function penMove(x, y) {                            // smooth: quadratic curves through midpoints
    var p = { x: x, y: y }; pts.push(p);
    var n = pts.length;
    penStyle(); ctx.beginPath();
    if (n === 2) {
      ctx.moveTo(pts[0].x, pts[0].y);
      ctx.lineTo((pts[0].x + p.x) / 2, (pts[0].y + p.y) / 2);
    } else {
      var a = pts[n - 3], b = pts[n - 2];
      ctx.moveTo((a.x + b.x) / 2, (a.y + b.y) / 2);
      ctx.quadraticCurveTo(b.x, b.y, (b.x + p.x) / 2, (b.y + p.y) / 2);
    }
    ctx.stroke();
  }
  function penEnd() {
    var n = pts.length;
    if (n < 2) return;
    penStyle(); ctx.beginPath();
    ctx.moveTo((pts[n - 2].x + pts[n - 1].x) / 2, (pts[n - 2].y + pts[n - 1].y) / 2);
    ctx.lineTo(pts[n - 1].x, pts[n - 1].y);
    ctx.stroke();
  }

  function erase(x0, y0, x1, y1) {                    // deletes everything within the chosen radius
    var r = +eraseEl.value;
    ctx.save();
    ctx.globalCompositeOperation = 'destination-out';
    ctx.lineWidth = r * 2; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    ctx.beginPath(); ctx.arc(x1, y1, r, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  /* --------------------------------------------------------------- bucket */
  function hexToRgb(h) {
    return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)];
  }

  // Fills the region enclosed by strokes. Returns false if the region is not enclosed
  // (it touches the page edge), so the caller can colour the page element instead.
  function floodFill(sx, sy) {
    var w = layer.width, h = layer.height;
    if (sx < 0 || sy < 0 || sx >= w || sy >= h) return false;
    var img = ctx.getImageData(0, 0, w, h), d = img.data;
    var s = (sy * w + sx) * 4, r0 = d[s], g0 = d[s + 1], b0 = d[s + 2], a0 = d[s + 3];
    var rgb = hexToRgb(color);
    var seen = new Uint8Array(w * h);
    function match(i) {
      var j = i * 4;
      return Math.abs(d[j] - r0) + Math.abs(d[j + 1] - g0) + Math.abs(d[j + 2] - b0) + Math.abs(d[j + 3] - a0) <= 160;
    }
    var stack = [sy * w + sx];
    seen[stack[0]] = 1;
    while (stack.length) {
      var p = stack.pop(), x = p % w, y = (p / w) | 0;
      if (x === 0 || y === 0 || x === w - 1 || y === h - 1) return false;   // leaked: not enclosed
      var j = p * 4;
      d[j] = rgb[0]; d[j + 1] = rgb[1]; d[j + 2] = rgb[2]; d[j + 3] = 255;
      var nb = [p - 1, p + 1, p - w, p + w];
      for (var k = 0; k < 4; k++) {
        var n = nb[k];
        if (!seen[n] && match(n)) { seen[n] = 1; stack.push(n); }
      }
    }
    ctx.putImageData(img, 0, 0);
    return true;
  }

  function elementFill(cx, cy) {                      // otherwise: colour the thing you clicked
    layer.style.pointerEvents = 'none';
    var el = document.elementFromPoint(cx, cy);
    layer.style.pointerEvents = 'auto';
    if (!el || el === document.documentElement) el = document.body;
    if (el.closest('#toolbox, .palette, .status, .menubar, .xp-overlay, [data-nozoom]')) return;
    if (!fills.has(el)) fills.set(el, el.getAttribute('style'));
    el.style.setProperty('background', color);
  }

  function bucket(e) {
    if (!floodFill(Math.floor(e.pageX), Math.floor(e.pageY))) elementFill(e.clientX, e.clientY);
    save();
  }

  /* ------------------------------------------------------------ magnifier */
  function buildWorld() {
    lensWorld.textContent = '';
    var clone = document.body.cloneNode(true);
    Array.prototype.forEach.call(clone.querySelectorAll('[data-nozoom], script'), function (n) { n.remove(); });
    clone.style.width = document.body.offsetWidth + 'px';
    clone.style.pointerEvents = 'none';
    lensWorld.style.width = document.documentElement.clientWidth + 'px';
    lensWorld.appendChild(clone);
    worldDirty = false; worldBuiltAt = performance.now();
  }

  function moveLens() {
    if (!lastClient) return;
    if (worldDirty && performance.now() - worldBuiltAt > 250) buildWorld();
    var z = +zoomEl.value, R = LENS_R;
    var px = lastClient.x + window.pageXOffset, py = lastClient.y + window.pageYOffset;
    lens.style.display = 'block';
    lens.style.left = (lastClient.x - LENS_CX) + 'px';
    lens.style.top = (lastClient.y - LENS_CY) + 'px';
    lensWorld.style.transform = 'translate(' + (R - px * z) + 'px,' + (R - py * z) + 'px) scale(' + z + ')';
    lctx.clearRect(0, 0, R * 2, R * 2);
    lctx.drawImage(layer, px - R / z, py - R / z, (R * 2) / z, (R * 2) / z, 0, 0, R * 2, R * 2);
  }

  new MutationObserver(function (recs) {
    for (var i = 0; i < recs.length; i++) {
      var t = recs[i].target, el = t.nodeType === 1 ? t : t.parentElement;
      if (el && !el.closest('[data-nozoom]')) { worldDirty = true; return; }
    }
  }).observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });

  /* ---------------------------------------------------------------- tools */
  function setTool(t) {
    tool = (tool === t) ? null : t;
    buttons.forEach(function (b) {
      var on = b.dataset.tool === tool;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    layer.style.pointerEvents = tool ? 'auto' : 'none';
    layer.style.cursor = (tool === 'pencil' || tool === 'pen' || tool === 'bucket') ? 'crosshair' : (tool ? 'none' : '');
    toolName.textContent = 'Tool: ' + (tool ? NAMES[tool] : 'none');
    ring.style.display = 'none'; lens.style.display = 'none';
    drawing = false;
    if (tool) fit();
    if (tool === 'magnifier') buildWorld();
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { setTool(b.dataset.tool); });
  });

  $('trash').addEventListener('click', function () {
    var run = function () {
      ctx.clearRect(0, 0, layer.width, layer.height);
      fills.forEach(function (prev, el) {
        if (prev === null) el.removeAttribute('style'); else el.setAttribute('style', prev);
      });
      fills.clear();
      try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
      if (tool === 'magnifier') moveLens();
    };
    if (window.xpConfirm) window.xpConfirm('Delete everything drawn on this page?', run); else run();
  });

  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && tool) setTool(tool); });

  /* ------------------------------------------------------------- palette */
  document.querySelector('.palette').addEventListener('click', function (e) {
    var sw = e.target.closest('[data-c]');
    if (!sw) return;
    color = sw.dataset.c;
    curColor.style.background = color;
    Array.prototype.forEach.call(document.querySelectorAll('.palette [data-c]'), function (i) {
      i.classList.toggle('sel', i === sw);
    });
  });

  /* -------------------------------------------------------------- sliders */
  function sliders() {
    zoomVal.textContent = (+zoomEl.value).toFixed(1) + 'x';
    eraseVal.textContent = eraseEl.value + 'px';
    var d = eraseEl.value * 2;
    ring.style.width = ring.style.height = d + 'px';
    if (tool === 'magnifier') moveLens();
  }
  zoomEl.addEventListener('input', sliders);
  eraseEl.addEventListener('input', sliders);

  /* -------------------------------------------------------------- pointer */
  layer.addEventListener('pointerdown', function (e) {
    if (!tool || e.button !== 0) return;
    e.preventDefault();
    if (tool === 'bucket') { bucket(e); return; }
    if (tool === 'magnifier') return;
    var x = e.pageX, y = e.pageY;
    fit();
    drawing = true; last = { x: x, y: y }; pts = [last];
    layer.setPointerCapture(e.pointerId);
    if (tool === 'pencil') grain(x, y, x, y);
    else if (tool === 'pen') penDot(x, y);
    else if (tool === 'eraser') erase(x, y, x, y);
  });

  layer.addEventListener('pointermove', function (e) {
    var x = e.pageX, y = e.pageY;
    lastClient = { x: e.clientX, y: e.clientY };
    if (tool === 'eraser') {
      ring.style.display = 'block'; ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
    } else if (tool === 'magnifier') {
      moveLens();
    }
    if (!drawing) return;
    if (tool === 'pencil') grain(last.x, last.y, x, y);
    else if (tool === 'pen') penMove(x, y);
    else if (tool === 'eraser') erase(last.x, last.y, x, y);
    last = { x: x, y: y };
  });

  function stop() {
    if (!drawing) return;
    if (tool === 'pen') penEnd();
    drawing = false; pts = [];
    save();
  }
  layer.addEventListener('pointerup', stop);
  layer.addEventListener('pointercancel', stop);
  layer.addEventListener('pointerleave', function () {
    ring.style.display = 'none'; lens.style.display = 'none'; lastClient = null;
  });

  window.addEventListener('scroll', function () { if (tool === 'magnifier') moveLens(); }, { passive: true });
  window.addEventListener('resize', function () { fit(); worldDirty = true; });
  window.addEventListener('load', function () { fit(); });
  if (window.ResizeObserver) new ResizeObserver(fit).observe(document.body);

  sliders();
  fit();
  restore();
})();