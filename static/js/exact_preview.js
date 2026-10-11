/* Aniq natija: har bir rasm serverda nashrdagi kod bilan moslanadi va aynan shu holatda ko'rsatiladi. */
window.ExactPreview = (function () {
  function csrf() { return document.querySelector('meta[name=csrf]').content; }
  function el(t, c, h) { var e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; }
  function open(o) {
    var ov = el('div', 'ex-ov'); var box = el('div', 'ex-box'); ov.appendChild(box);
    var head = el('div', 'ex-h', '<b>Aniq natija — nashrdan keyin aynan shunday bo‘ladi</b>'); var x = el('button', 'btn sm', '✕'); x.type = 'button'; x.onclick = function () { ov.remove(); }; head.appendChild(x); box.appendChild(head);
    var info = el('div', 'hint', 'Quyidagi rasmlar serverda nashr kodi bilan tayyorlangan: o‘lcham, qirqish va moslash usuli real. ' + (o.size && o.size !== 'orig' ? '' : 'O‘lcham tanlanmagan — asl holicha (Instagram uchun nisbat avtomatik moslanishi mumkin).')); box.appendChild(info);
    var grid = el('div', 'ex-grid'); box.appendChild(grid);
    ov.addEventListener('click', function (e) { if (e.target === ov) ov.remove(); });
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { ov.remove(); document.removeEventListener('keydown', esc); } });
    document.body.appendChild(ov);
    var list = [];
    (o.existing || []).forEach(function (id) { list.push({ aid: id }); });
    (o.files || []).forEach(function (f) { if ((f.type || '').indexOf('video') !== 0) list.push({ file: f }); });
    (o.cloud || []).forEach(function (id) { list.push({ cloud_id: id }); });
    if (!list.length) { grid.innerHTML = '<div class="muted" style="padding:16px">Ko‘rsatish uchun rasm yo‘q (video kadrlari bu rejimda ko‘rsatilmaydi).</div>'; return; }
    var plats = o.plats && o.plats.length ? o.plats : [''];
    list.forEach(function (it, i) {
      plats.forEach(function (pl) {
        var card = el('div', 'ex-c', '<div class="muted" style="font-size:12px">⏳ ' + (i + 1) + '-rasm' + (pl ? ' · ' + pl : '') + '…</div>'); grid.appendChild(card);
        var fd = new FormData(); fd.append('size', o.size || 'orig'); fd.append('fit', o.fit || 'pad'); fd.append('plat', pl);
        fd.append('cx', (o.crop || {}).x == null ? .5 : o.crop.x); fd.append('cy', (o.crop || {}).y == null ? .5 : o.crop.y); fd.append('cz', (o.crop || {}).z || 1);
        if (it.aid) fd.append('aid', it.aid); if (it.cloud_id) fd.append('cloud_id', it.cloud_id); if (it.file) fd.append('file', it.file, it.file.name);
        fetch('/kalendar/aniq-korinish/', { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf() } }).then(function (r) {
          if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || 'Xato'); });
          var d = r.headers.get('X-Dims'); return r.blob().then(function (b) { return { b: b, d: d }; });
        }).then(function (x) {
          card.innerHTML = ''; var im = el('img'); im.src = URL.createObjectURL(x.b); card.appendChild(im);
          card.appendChild(el('div', 'hint', (i + 1) + '-rasm' + (pl ? ' · ' + pl : '') + ' · ' + (x.d || '').replace('x', '×') + ' px'));
        }).catch(function (e) { card.innerHTML = '<div class="hint bad">' + (e.message || 'Xato') + '</div>'; });
      });
    });
  }
  return { open: open };
})();
