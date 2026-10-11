/* Oddiy rasm muharriri: kesish (nisbat bo'yicha), siljitish, kattalashtirish, aylantirish. ImageEditor.open(file, {ratio, onDone(file)}) */
(function (w) {
  var RATIOS = [['Asl nisbat', 0], ['1:1', 1], ['4:5', 4 / 5], ['1.91:1', 1.91], ['9:16', 9 / 16], ['16:9', 16 / 9]];
  var OUT = { 1: [1080, 1080], 0.8: [1080, 1350], 1.91: [1080, 566], 0.5625: [1080, 1920], 1.7778: [1920, 1080] };
  function outSize(r, iw, ih) {
    for (var k in OUT) { if (Math.abs(parseFloat(k) - r) < 0.01) return OUT[k]; }
    var W = Math.min(Math.max(iw, ih), 2000); return r >= 1 ? [W, Math.round(W / r)] : [Math.round(W * r), W];
  }
  function el(tag, css, html) { var e = document.createElement(tag); if (css) e.style.cssText = css; if (html) e.innerHTML = html; return e; }

  w.ImageEditor = {
    open: function (file, opt) {
      opt = opt || {};
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () { start(img); };
      img.onerror = function () { URL.revokeObjectURL(url); alert('Rasmni ochib bo\'lmadi.'); };
      img.src = url;

      function start(img) {
        var rot = 0, ratio = opt.ratio || 0, scale = 1, tx = 0, ty = 0, W = 0, H = 0, drag = null;
        var ov = el('div', 'position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:9999;display:flex;align-items:center;justify-content:center;padding:12px');
        var box = el('div', 'background:var(--surface,#fff);color:var(--fg,#111);border-radius:16px;padding:16px;max-width:620px;width:100%;max-height:96vh;overflow:auto');
        box.innerHTML = '<div style="font-weight:700;margin-bottom:8px">✂ Rasmni tahrirlash</div>';
        var rb = el('div', 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px');
        var cv = el('canvas', 'width:100%;max-width:560px;display:block;margin:0 auto;border-radius:10px;background:#222;touch-action:none;cursor:grab');
        var zr = el('input'); zr.type = 'range'; zr.min = 1; zr.max = 4; zr.step = 0.01; zr.value = 1; zr.style.cssText = 'width:100%;margin-top:10px';
        var hint = el('div', 'font-size:12px;color:var(--muted,#666);margin-top:4px', 'Sudrab siljiting, g\'ildirak yoki slayder bilan kattalashtiring.');
        var bar = el('div', 'display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;justify-content:flex-end');
        function btn(t, cls, fn) { var b = el('button', '', t); b.type = 'button'; b.className = 'btn ' + (cls || ''); b.onclick = fn; return b; }
        var btns = [];
        RATIOS.forEach(function (r) { var b = btn(r[0], 'sm', function () { ratio = r[1]; setup(); mark(); }); b.dataset.r = r[1]; rb.appendChild(b); btns.push(b); });
        function mark() { btns.forEach(function (b) { var on = Math.abs(parseFloat(b.dataset.r) - ratio) < 0.001; b.style.borderColor = on ? 'var(--brand,#e11d2e)' : ''; b.style.fontWeight = on ? '800' : ''; }); }
        bar.appendChild(btn('⟲ Aylantirish', 'sm', function () { rot = (rot + 1) % 4; setup(true); }));
        bar.appendChild(btn('Tiklash', 'sm', function () { rot = 0; setup(); }));
        bar.appendChild(btn('Bekor qilish', '', close));
        bar.appendChild(btn('✓ Qo\'llash', 'primary', apply));
        box.appendChild(rb); box.appendChild(cv); box.appendChild(zr); box.appendChild(hint); box.appendChild(bar);
        ov.appendChild(box); document.body.appendChild(ov);

        function dims() { return rot % 2 ? [img.naturalHeight, img.naturalWidth] : [img.naturalWidth, img.naturalHeight]; }
        function minScale() { var d = dims(); return Math.max(W / d[0], H / d[1]); }
        function clamp() {
          var d = dims(), s = scale, mx = Math.max(0, (d[0] * s - W) / 2), my = Math.max(0, (d[1] * s - H) / 2);
          tx = Math.min(mx, Math.max(-mx, tx)); ty = Math.min(my, Math.max(-my, ty));
        }
        function setup(keepZoom) {
          var d = dims(), r = ratio || d[0] / d[1], maxW = 560, maxH = 440;
          W = r >= maxW / maxH ? maxW : Math.round(maxH * r); H = Math.round(W / r);
          if (H > maxH) { H = maxH; W = Math.round(H * r); }
          cv.width = W; cv.height = H;
          var m = minScale(); scale = keepZoom ? Math.max(m, scale) : m; tx = ty = 0;
          zr.min = m; zr.max = m * 4; zr.value = scale; draw();
        }
        function draw(k, c2) {
          k = k || 1; var c = c2 || cv.getContext('2d'), d = dims();
          c.save(); c.fillStyle = '#222'; c.fillRect(0, 0, W * k, H * k);
          c.translate(W * k / 2 + tx * k, H * k / 2 + ty * k); c.rotate(rot * Math.PI / 2); c.scale(scale * k, scale * k);
          c.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2); c.restore();
        }
        zr.oninput = function () { scale = parseFloat(zr.value); clamp(); draw(); };
        cv.onwheel = function (e) { e.preventDefault(); var m = minScale(); scale = Math.min(m * 4, Math.max(m, scale * (e.deltaY < 0 ? 1.08 : 0.93))); zr.value = scale; clamp(); draw(); };
        cv.onpointerdown = function (e) { drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty }; cv.setPointerCapture(e.pointerId); cv.style.cursor = 'grabbing'; };
        cv.onpointermove = function (e) {
          if (!drag) return; var f = W / cv.getBoundingClientRect().width;
          tx = drag.tx + (e.clientX - drag.x) * f; ty = drag.ty + (e.clientY - drag.y) * f; clamp(); draw();
        };
        cv.onpointerup = function () { drag = null; cv.style.cursor = 'grab'; };
        function close() { document.body.removeChild(ov); URL.revokeObjectURL(url); }
        function apply() {
          var d = dims(), os = outSize(ratio || d[0] / d[1], d[0], d[1]), k = os[0] / W;
          var out = document.createElement('canvas'); out.width = os[0]; out.height = os[1];
          var save = [W, H]; draw(k, out.getContext('2d')); W = save[0]; H = save[1];
          out.toBlob(function (b) {
            if (!b) { alert('Saqlab bo\'lmadi.'); return; }
            var name = file.name.replace(/\.[^.]+$/, '') + '_tahrir.jpg';
            var nf = new File([b], name, { type: 'image/jpeg' }); close(); if (opt.onDone) opt.onDone(nf);
          }, 'image/jpeg', 0.92);
        }
        setup(); mark();
      }
    }
  };
})(window);
