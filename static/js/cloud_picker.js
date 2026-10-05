/* «Cloudflare'dan tanlash» oynasi (post formasi va post sahifasida umumiy).
   CloudPicker.open({kinds:'image,video', multi:true, onPick:function(files){...}}) ; files: [{id,name,kind,url,tags}] */
window.CloudPicker = (function () {
  var el, grid, q, cnt, sel = {}, list = [], opt = {}, timer;
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function build() {
    el = document.createElement('div');
    el.style.cssText = 'display:none;position:fixed;inset:0;z-index:95;background:rgba(0,0,0,.55);align-items:center;justify-content:center;padding:12px';
    el.innerHTML = '<div class="card" style="max-width:860px;width:100%;max-height:90vh;display:flex;flex-direction:column;gap:10px">' +
      '<div class="row sb"><b>☁ Cloudflare kutubxonasi</b><button type="button" class="btn sm" data-x="close">✕ Yopish</button></div>' +
      '<input type="text" data-x="q" placeholder="Qidirish: fayl nomi, teg yoki post nomi">' +
      '<div data-x="grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;overflow:auto;min-height:120px"></div>' +
      '<div class="row sb"><span class="hint" data-x="cnt"></span><button type="button" class="btn primary" data-x="ok">Tanlanganlarni qo\'shish</button></div></div>';
    document.body.appendChild(el);
    grid = el.querySelector('[data-x=grid]'); q = el.querySelector('[data-x=q]'); cnt = el.querySelector('[data-x=cnt]');
    el.querySelector('[data-x=close]').onclick = close;
    el.addEventListener('click', function (e) { if (e.target === el) close(); });
    q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(load, 300); });
    el.querySelector('[data-x=ok]').onclick = function () {
      var out = Object.keys(sel).map(function (k) { return sel[k]; }).filter(function (f) { return f.url; });
      close(); if (out.length && opt.onPick) opt.onPick(out);
    };
    grid.addEventListener('click', function (e) {
      var c = e.target.closest('.cpi'); if (!c) return; var f = list[+c.dataset.i];
      if (sel[f.id]) delete sel[f.id]; else { if (!opt.multi) sel = {}; sel[f.id] = f; }
      paint();
    });
  }
  function paint() {
    grid.querySelectorAll('.cpi').forEach(function (x) { var f = list[+x.dataset.i]; x.style.outline = sel[f.id] ? '3px solid var(--brand)' : ''; });
    cnt.textContent = 'Tanlandi: ' + Object.keys(sel).length;
  }
  function load() {
    grid.innerHTML = '<span class="hint" style="grid-column:1/-1">Yuklanmoqda…</span>';
    fetch('/cloudflare/tanlash/?kind=' + encodeURIComponent(opt.kinds || 'image,video') + '&q=' + encodeURIComponent(q.value)).then(function (r) { return r.json(); }).then(function (r) {
      if (r.error) { grid.innerHTML = '<span class="hint bad" style="grid-column:1/-1">' + esc(r.error) + '</span>'; return; }
      list = r.files; var h = '';
      if (!list.length) h = '<span class="hint" style="grid-column:1/-1">Mos fayl topilmadi. Avval fayl yuklang yoki «Cloudflare» menyusini tekshiring.</span>';
      list.forEach(function (f, i) {
        var th = f.url ? (f.kind === 'video' ? '<video src="' + f.url + '#t=0.1" muted preload="metadata" style="width:100%;height:90px;object-fit:cover;border-radius:8px"></video>' :
          '<img src="' + f.url + '" loading="lazy" style="width:100%;height:90px;object-fit:cover;border-radius:8px">') : '<div style="height:90px;display:flex;align-items:center;justify-content:center" class="hint">Yuklanmoqda</div>';
        h += '<div class="cpi" data-i="' + i + '" style="cursor:pointer;font-size:11px;border-radius:8px;padding:4px;background:var(--surface-2)">' + th + '<div>' + esc((f.name || '').slice(0, 22)) + '</div>' +
          '<div class="hint">' + esc(f.size + ' · ' + f.at) + '</div>' + (f.tags && f.tags.length ? '<div style="color:var(--brand-2)">#' + f.tags.map(esc).join(' #') + '</div>' : '') + '</div>';
      });
      grid.innerHTML = h; paint();
    }).catch(function () { grid.innerHTML = '<span class="hint bad" style="grid-column:1/-1">Server bilan aloqa xatosi.</span>'; });
  }
  function close() { el.style.display = 'none'; }
  return { open: function (o) { opt = o || {}; if (!el) build(); sel = {}; q.value = ''; el.style.display = 'flex'; load(); } };
})();
