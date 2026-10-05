/* Kalendar: kunni bosganda o'ng tomondan shu kunning postlar ro'yxati chiqadi; postni bosganda o'sha post ochiladi. */
(function () {
  var cg = document.querySelector('.cg'); if (!cg) return;
  var D = {}; try { D = JSON.parse(document.getElementById('calData').textContent) || {}; } catch (e) {}
  var M = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];
  var W = ['Yakshanba', 'Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba'];
  var dw = document.getElementById('dw'), sc = document.getElementById('dwScrim'), bd = document.getElementById('dwBody');
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function openDay(day) {
    var a = day.split('-'), dt = new Date(+a[0], +a[1] - 1, +a[2]), L = D[day] || [];
    document.querySelectorAll('.cg .d.sel').forEach(function (x) { x.classList.remove('sel'); });
    var c = document.querySelector('.cg .d[data-day="' + day + '"]'); if (c) c.classList.add('sel');
    document.getElementById('dwTitle').textContent = dt.getDate() + ' ' + M[dt.getMonth()] + ', ' + W[dt.getDay()];
    document.getElementById('dwSub').textContent = L.length ? (L.length + ' ta post') : "Bu kunda post yo'q";
    var h = '';
    L.forEach(function (p) {
      var th = p.th ? '<img class="th" loading="lazy" src="' + p.th + '" alt="">' : '<div class="th" style="display:flex;align-items:center;justify-content:center;font-size:12px;color:#64748b">' + esc(p.fmt) + '</div>';
      var rule = p.rule === 'block' ? ' <span style="color:#ef4444">⚠ qoida to\'sqinligi</span>' : p.rule === 'warn' ? ' <span style="color:#f59e0b">ogohlantirish</span>' : '';
      h += '<a class="dw-i" href="/kalendar/' + p.id + '/">' + th + '<div style="min-width:0"><div class="tt">' + esc(p.title) + '</div>' +
        '<div class="mm"><b>' + p.t + '</b> · ' + esc(p.pl.join(' / ') || '—') + ' · ' + esc(p.fmt) + '</div>' +
        '<div class="mm"><span class="bd" style="background:' + p.c + '">' + esc(p.stl) + '</span>' + rule + '</div></div></a>';
    });
    bd.innerHTML = h || '<div class="muted" style="padding:20px 4px">Bu kunga hali post rejalashtirilmagan.</div>';
    var ad = document.getElementById('dwAdd'); if (ad) ad.href = '/kalendar/yangi/?date=' + day;
    dw.classList.add('on'); sc.classList.add('on'); dw.setAttribute('aria-hidden', 'false');
  }
  function closeDw() { dw.classList.remove('on'); sc.classList.remove('on'); dw.setAttribute('aria-hidden', 'true'); document.querySelectorAll('.cg .d.sel').forEach(function (x) { x.classList.remove('sel'); }); }
  cg.addEventListener('click', function (e) { var c = e.target.closest('.d[data-day]'); if (!c || e.target.closest('.n a')) return; e.preventDefault(); openDay(c.dataset.day); });
  cg.addEventListener('keydown', function (e) { if (e.key === 'Enter') { var c = e.target.closest('.d[data-day]'); if (c) openDay(c.dataset.day); } });
  document.getElementById('dwClose').onclick = closeDw; sc.onclick = closeDw;
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDw(); });
})();

/* Kalendar: postni sudrab boshqa kunga ko'chirish (vaqt o'zgarmaydi, faqat sana). */
(function () {
  var cg = document.querySelector('.cg'); if (!cg) return;
  var dragId = null;
  function toast(t, bad) { var d = document.createElement('div'); d.className = 'dd-toast' + (bad ? ' bad' : ''); d.textContent = t; document.body.appendChild(d); setTimeout(function () { d.remove(); }, bad ? 4500 : 1800); }
  function csrf() { var m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; }
  cg.addEventListener('dragstart', function (e) { var p = e.target.closest('.p[data-id]'); if (!p) return; dragId = p.dataset.id; p.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', dragId); });
  cg.addEventListener('dragend', function (e) { dragId = null; document.querySelectorAll('.cg .dragging,.cg .over').forEach(function (x) { x.classList.remove('dragging', 'over'); }); });
  cg.addEventListener('dragover', function (e) { var c = e.target.closest('.d[data-day]'); if (!c || !dragId) return; e.preventDefault(); document.querySelectorAll('.cg .over').forEach(function (x) { if (x !== c) x.classList.remove('over'); }); c.classList.add('over'); });
  cg.addEventListener('drop', function (e) {
    var c = e.target.closest('.d[data-day]'); if (!c || !dragId) return; e.preventDefault(); c.classList.remove('over');
    var id = dragId, day = c.dataset.day; dragId = null;
    var fd = new FormData(); fd.append('date', day); fd.append('csrfmiddlewaretoken', csrf());
    fetch('/kalendar/' + id + '/koch/', { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf() } }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) { if (x.ok && x.j.ok) { toast('Ko\u2019chirildi: ' + x.j.when); setTimeout(function () { location.reload(); }, 700); } else { toast((x.j && x.j.error) || 'Ko\u2019chirib bo\u2019lmadi', true); } })
      .catch(function () { toast('Server bilan aloqa xatosi', true); });
  });
})();
