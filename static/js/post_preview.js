/* Post oldindan ko'rinishi: Telegram / Instagram / YouTube. cfg.get() -> {text, mt, sel:{platform:[{name,handle}]}, media:[{url,kind}]} */
window.PostPreview = function (cfg) {
  var $ = function (i) { return document.getElementById(i); };
  var LBL = { text: 'Matn', image: 'Rasm', video: 'Video', album: 'Albom', reel: 'Reels (9:16)', short: 'Shorts (9:16)', story: 'Stories (9:16)', carousel: 'Karusel' };
  var idx = 0;
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }
  function tags(s) { return esc(s).replace(/(#[\wА-Яа-яЁёʻ'’_]+)/g, '<span class="pv-tag">$1</span>'); }
  function warn(id, list) { $(id).innerHTML = list.map(function (w) { return '<div class="pv-warn' + (w[0] ? ' bad' : '') + '">' + w[1] + '</div>'; }).join(''); }
  function count(id, n, max) { $(id).innerHTML = (n > max ? '<b class="bad">' : '<b>') + n + '</b> / ' + max; }
  var dims = {};          // url -> {w,h}
  var cur = null;         // oxirgi cfg.get()
  var clampN = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  function naturalOf(media) { var m = media && media.length && media[idx % media.length]; return m && dims[m.url] ? dims[m.url].w / dims[m.url].h : 0; }
  function frameRatio(plat, mt, d, media) {
    if (d.ratio) return d.ratio;
    var nat = naturalOf(media), tall = (mt === 'reel' || mt === 'short' || mt === 'story');
    if (plat === 'instagram') return tall ? 9 / 16 : (nat ? clampN(nat, 0.8, 1.91) : 1);
    if (plat === 'youtube') return tall ? 9 / 16 : 16 / 9;
    return nat ? clampN(nat, 0.56, 1.9) : 4 / 3;     // telegram
  }
  function setMedia(el, label, media, plat, mt, d, ratioOverride) {
    var r = ratioOverride || frameRatio(plat, mt, d, media);
    el.className = 'pv-media' + (media && media.length > 1 ? ' clk' : '');
    el.style.aspectRatio = String(r); el.style.width = 'min(100%,' + Math.round(560 * r) + 'px)'; el.style.margin = '0 auto';
    el.dataset.r = r;
    if (media && media.length) {
      var m = media[idx % media.length];
      var h = (m.kind === 'image' ? '<img class="bg" src="' + m.url + '" alt="">' : '') +
        (m.kind === 'video' ? '<video class="fit" src="' + m.url + '" muted loop autoplay playsinline preload="metadata"></video>' : '<img class="fit" src="' + m.url + '" alt="">');
      if (media.length > 1) h += '<span class="cnt">' + ((idx % media.length) + 1) + '/' + media.length + ' · bosib almashtiring</span>';
      el.innerHTML = h;
      var f = el.querySelector('.fit');
      var got = function (w, hh) { if (w && hh && (!dims[m.url] || dims[m.url].w !== w)) { dims[m.url] = { w: w, h: hh }; render(); } else place(el); };
      if (f.tagName === 'VIDEO') { f.onloadedmetadata = function () { got(f.videoWidth, f.videoHeight); }; if (f.readyState > 0) got(f.videoWidth, f.videoHeight); }
      else { f.onload = function () { got(f.naturalWidth, f.naturalHeight); }; if (f.complete && f.naturalWidth) got(f.naturalWidth, f.naturalHeight); }
      place(el);
    } else el.innerHTML = '<span>' + label + '</span>';
  }
  function overlays(box, mt, media, plat) {
    if (!box) return; [].slice.call(box.querySelectorAll('.pv-safe,.pv-dots')).forEach(function (n) { n.remove(); });
    var safe = $('pvSafe'), tall = (mt === 'story' || mt === 'reel' || mt === 'short');
    if (tall && safe && safe.checked && !box.hidden) {
      var z = document.createElement('div'); z.className = 'pv-safe';
      z.innerHTML = '<i class="t"></i><i class="b"></i><span style="top:4px">profil / sarlavha</span><span style="bottom:4px">javob / tugmalar</span>'; box.appendChild(z);
    }
    if (media && media.length > 1 && (mt === 'carousel' || mt === 'album') && plat !== 'youtube') {
      var dv = document.createElement('div'); dv.className = 'pv-dots';
      for (var i = 0; i < media.length; i++) dv.innerHTML += '<b' + (i === idx % media.length ? ' class="on"' : '') + '></b>'; box.appendChild(dv);
    }
  }
  function geom(box) {
    var f = box.querySelector('.fit'), d = cur || {}; if (!f) return null;
    var m = (d.media || [])[idx % ((d.media || []).length || 1)], dm = m && dims[m.url]; if (!dm) return null;
    var fw = box.clientWidth, fh = box.clientHeight; if (!fw || !fh) return null;
    if (m.exact) return { f: f, fw: fw, fh: fh, sw: fw, sh: fh, ox: 0, oy: 0, pad: false, c: { x: .5, y: .5, z: 1 }, left: 0, top: 0 };
    var forced = !!d.ratio, pad = forced && d.fit === 'pad', c = d.crop || { x: .5, y: .5, z: 1 };
    var s = pad ? Math.min(fw / dm.w, fh / dm.h) : Math.max(fw / dm.w, fh / dm.h) * (forced ? c.z : 1);
    var sw = dm.w * s, sh = dm.h * s;
    return { f: f, fw: fw, fh: fh, sw: sw, sh: sh, ox: Math.max(0, sw - fw), oy: Math.max(0, sh - fh), pad: pad, c: c,
      left: sw >= fw ? -(sw - fw) * c.x : (fw - sw) / 2, top: sh >= fh ? -(sh - fh) * c.y : (fh - sh) / 2 };
  }
  function place(box) {
    var g = geom(box); if (!g) return;
    var st = g.f.style; st.position = 'absolute'; st.width = g.sw + 'px'; st.height = g.sh + 'px'; st.left = g.left + 'px'; st.top = g.top + 'px'; st.objectFit = 'fill'; st.inset = 'auto';
    var bg = box.querySelector('.bg'); if (bg) bg.style.display = g.pad ? 'block' : 'none';
  }
  function layoutAll() { document.querySelectorAll('.pv-media').forEach(function (b) { if (!b.hidden) place(b); }); }
  // sudrab siljitish / kattalashtirish (faqat o'lcham tanlanganda va "qirqish" rejimida)
  var drag = null;
  document.addEventListener('pointerdown', function (e) {
    var box = e.target.closest && e.target.closest('.pv-media'); if (!box || !cur || !cur.ratio || cur.fit === 'pad') return;
    var g = geom(box); if (!g || (g.ox < 1 && g.oy < 1)) return;
    drag = { box: box, x: e.clientX, y: e.clientY, cx: g.c.x, cy: g.c.y, g: g }; box.setPointerCapture(e.pointerId); box.classList.add('drg'); e.preventDefault();
  });
  document.addEventListener('pointermove', function (e) {
    if (!drag) return; var g = drag.g, rect = drag.box.getBoundingClientRect(), k = g.fw / rect.width;
    var cx = g.ox > 1 ? clampN(drag.cx - (e.clientX - drag.x) * k / g.ox, 0, 1) : drag.cx, cy = g.oy > 1 ? clampN(drag.cy - (e.clientY - drag.y) * k / g.oy, 0, 1) : drag.cy;
    if (cfg.setCrop) cfg.setCrop(cx, cy, null); cur.crop = { x: cx, y: cy, z: (cur.crop || {}).z || 1 }; layoutAll();
  });
  document.addEventListener('pointerup', function () { if (drag) { drag.box.classList.remove('drg'); drag = null; } });
  document.addEventListener('wheel', function (e) {
    var box = e.target.closest && e.target.closest('.pv-media'); if (!box || !cur || !cur.ratio || cur.fit === 'pad') return;
    e.preventDefault(); var c = cur.crop || { x: .5, y: .5, z: 1 }, z = clampN(c.z * (e.deltaY < 0 ? 1.06 : 0.94), 1, 4);
    if (cfg.setCrop) cfg.setCrop(null, null, z); cur.crop = { x: c.x, y: c.y, z: z }; layoutAll();
  }, { passive: false });
  window.addEventListener('resize', layoutAll);

  function render() {
    var d = cfg.get(), text = d.text || '', mt = d.mt || 'text', sel = d.sel || {}, media = d.media || [];
    cur = d;
    var hasMedia = mt !== 'text' || media.length > 0, lbl = LBL[mt] || mt;
    document.querySelectorAll('.pv-tab').forEach(function (t) { t.querySelector('.dot').hidden = !sel[t.dataset.p]; });
    // Telegram
    var t = sel.telegram && sel.telegram[0]; $('tgName').textContent = t ? t.name : 'Kanal';
    var m = $('tgMedia'); m.hidden = !hasMedia; if (hasMedia) setMedia(m, lbl, media, 'telegram', mt, d); else m.innerHTML = '';
    $('tgText').innerHTML = text ? tags(text) : '<span class="muted">Matn shu yerda ko\'rinadi…</span>';
    var lim = hasMedia ? 1024 : 4096; count('tgCount', text.length, lim); $('tgNote').textContent = hasMedia ? 'Rasm/video bilan: caption' : 'Oddiy xabar';
    warn('tgWarn', text.length > lim ? [[1, 'Matn ' + lim + ' belgidan oshdi' + (hasMedia ? ' (caption chegarasi). Qisqartiring.' : '.')]] : []);
    // Instagram
    var ig = sel.instagram && sel.instagram[0], nm = ig ? (ig.handle || ig.name) : 'akkaunt'; $('igName').textContent = nm; $('igName2').textContent = nm;
    setMedia($('igMedia'), mt === 'text' ? 'Media kerak' : lbl, media, 'instagram', mt, d);
    var gr = $('igGrid'); if (gr) { gr.style.display = media.length && mt !== 'story' ? 'block' : 'none'; if (media.length) setMedia(gr, '', media, 'instagram', mt, d, 3 / 4); gr.style.width = '96px'; gr.style.margin = '0'; }
    overlays($('igMedia'), mt, media, 'instagram'); overlays($('tgMedia'), mt, media, 'telegram');
    var tb = $('tgBtns'); if (tb) tb.innerHTML = (d.buttons || []).map(function (r) { r = [].concat(r); return '<div class="tg-row">' + r.map(function (b) { return '<span>' + esc(b) + '</span>'; }).join('') + '</div>'; }).join('');
    var cut = text.length > 125 ? text.slice(0, 125) : text;
    $('igText').innerHTML = text ? (text.length > 125 ? tags(cut) + '… <span class="muted">ko\'proq</span>' : tags(text)) : '<span class="muted">Caption shu yerda…</span>';
    count('igCount', text.length, 2200); $('igNote').textContent = 'Birinchi 125 belgi ko\'rinadi';
    var ht = (text.match(/#[^\s#]+/g) || []).length, w = [];
    if (mt === 'text' && !media.length) w.push([1, 'Instagram\'da post uchun rasm yoki video shart.']);
    if (text.length > 2200) w.push([1, 'Caption 2200 belgidan oshdi.']);
    if (ht > 30) w.push([1, 'Hashtaglar 30 tadan oshdi (' + ht + ').']); else if (ht > 10) w.push([0, 'Hashtag ' + ht + ' ta — 3–10 ta tavsiya etiladi.']);
    warn('igWarn', w);
    // YouTube
    var first = text.split('\n')[0].trim(), ytT = (d.ytTitle || first).slice(0, 100);
    var ym = $('ytMedia');
    if (media.length) setMedia(ym, '', media, 'youtube', mt, d); else { ym.className = 'pv-media'; ym.style.aspectRatio = String(frameRatio('youtube', mt, d, media)); ym.innerHTML = '<span>▶ ' + (mt === 'video' || mt === 'short' ? lbl : 'Video kerak') + '</span>'; }
    $('ytTitle').textContent = ytT || 'Sarlavha (matnning birinchi qatoridan olinadi)';
    var yc = sel.youtube && sel.youtube[0]; $('ytChan').textContent = (yc ? yc.name : 'Kanal') + ' · hozirgina';
    $('ytDesc').innerHTML = text ? tags(text) : '<span class="muted">Tavsif shu yerda…</span>';
    count('ytCount', text.length, 5000); $('ytNote').textContent = 'Sarlavha: ' + ytT.length + ' / 100';
    var yw = []; if (mt !== 'video' && mt !== 'short') yw.push([1, 'YouTube uchun post turi «Video» yoki «Shorts» bo\'lishi kerak.']);
    if (!ytT) yw.push([1, 'Sarlavha uchun matnning birinchi qatori kerak.']); if (!d.ytTitle && first.length > 100) yw.push([0, 'Sarlavha 100 belgiga qisqartiriladi.']);
    if (text.length > 5000) yw.push([1, 'Tavsif 5000 belgidan oshdi.']);
    warn('ytWarn', yw);
    var fi = $('frameInfo'); if (fi) { var r0 = d.ratio, names = { 0.8: '4:5', 1: '1:1', 1.91: '1.91:1', 0.5625: '9:16', 1.7778: '16:9' }, nm0 = ''; for (var k in names) if (r0 && Math.abs(parseFloat(k) - r0) < 0.01) nm0 = names[k];
      fi.textContent = r0 ? ('Kadr: ' + nm0 + (d.fit === 'pad' ? ' · butun kadr, chetlari xira fon' : ' · qirqish: rasmni sudrab siljiting, g\'ildirak bilan kattalashtiring')) : 'Kadr: asl nisbat (o\'lcham tanlanmagan)'; }
    layoutAll();
  }
  document.querySelectorAll('.pv-tab').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.pv-tab').forEach(function (x) { x.classList.toggle('on', x === b); });
      document.querySelectorAll('.pv-pane').forEach(function (p) { p.classList.toggle('on', p.id === 'pv-' + b.dataset.p); });
    });
  });
  ['tgMedia', 'igMedia', 'ytMedia'].forEach(function (id) {
    $(id).addEventListener('click', function (e) { if (drag) return; var m = cfg.get().media || []; if (m.length > 1) { idx++; render(); } });
  });
  if ($('pvSafe')) $('pvSafe').addEventListener('change', render);
  render();
  return { render: render, show: function (p) { var b = document.querySelector('.pv-tab[data-p=' + p + ']'); if (b) b.click(); } };
};
