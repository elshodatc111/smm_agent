/* Forma qoralamasini brauzerda avtomatik saqlaydi (fayllar bundan mustasno) va qaytadan ochilganda tiklashni taklif qiladi. */
(function () {
  var form = document.getElementById('cform'); if (!form) return;
  var key = 'smm-draft:' + location.pathname;
  var TTL = 7 * 24 * 3600 * 1000;
  var SKIP = { csrfmiddlewaretoken: 1, files: 1, cloud_ids: 1 };
  function store() { try { return window.localStorage; } catch (e) { return null; } }
  var ls = store(); if (!ls) return;
  function collect() {
    var d = {}, n = 0;
    [].slice.call(form.elements).forEach(function (el) {
      if (!el.name || SKIP[el.name] || el.type === 'file' || el.type === 'submit' || el.type === 'button' || el.type === 'password') return;
      if (el.type === 'checkbox') { if (el.checked) (d[el.name] = d[el.name] || []).push(el.value); return; }
      if (el.type === 'radio') { if (el.checked) d[el.name] = el.value; return; }
      if (el.value) { d[el.name] = el.value; if (['id_text', 'id_title', 'id_yt_title'].indexOf(el.id) >= 0) n += el.value.length; }
    });
    return { d: d, n: n };
  }
  var timer = null, restoring = false;
  function save() {
    if (restoring) return; var c = collect();
    try { if (c.n < 3 && !(c.d.targets || []).length) { ls.removeItem(key); return; } ls.setItem(key, JSON.stringify({ t: Date.now(), d: c.d })); } catch (e) {}
    var s = document.getElementById('draftState'); if (s) s.textContent = 'Qoralama avtomatik saqlandi · ' + new Date().toTimeString().slice(0, 5);
  }
  function later() { clearTimeout(timer); timer = setTimeout(save, 700); }
  form.addEventListener('input', later); form.addEventListener('change', later);
  form.addEventListener('submit', function () { try { ls.removeItem(key); } catch (e) {} });
  var saved = null; try { saved = JSON.parse(ls.getItem(key) || 'null'); } catch (e) {}
  var bar = document.createElement('div'); bar.className = 'hint'; bar.id = 'draftState'; bar.style.margin = '6px 0 0';
  form.appendChild(bar);
  if (!saved || !saved.d || Date.now() - saved.t > TTL) { try { ls.removeItem(key); } catch (e) {} return; }
  var cur = collect();
  if (JSON.stringify(cur.d) === JSON.stringify(saved.d)) return;
  var box = document.createElement('div'); box.className = 'flash'; box.style.cssText = 'display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px';
  var when = new Date(saved.t); box.innerHTML = '<span>📝 Saqlanmagan qoralama topildi (' + when.toLocaleDateString() + ' ' + when.toTimeString().slice(0, 5) + '). Tiklaysizmi?</span>';
  var ok = document.createElement('button'); ok.type = 'button'; ok.className = 'btn sm primary'; ok.textContent = 'Tiklash';
  var no = document.createElement('button'); no.type = 'button'; no.className = 'btn sm'; no.textContent = 'O‘chirib tashlash';
  box.appendChild(ok); box.appendChild(no); form.insertBefore(box, form.firstChild.nextSibling);
  ok.onclick = function () {
    restoring = true;
    [].slice.call(form.elements).forEach(function (el) {
      if (!el.name || SKIP[el.name] || el.type === 'file') return;
      var v = saved.d[el.name];
      if (el.type === 'checkbox') { var on = (v || []).indexOf(el.value) >= 0; if (el.checked !== on) { el.checked = on; el.dispatchEvent(new Event('change', { bubbles: true })); } return; }
      if (el.type === 'radio') { el.checked = (v === el.value); return; }
      if (v !== undefined && el.type !== 'hidden') { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }
      else if (v !== undefined) el.value = v;
    });
    restoring = false; box.remove(); save();
  };
  no.onclick = function () { try { ls.removeItem(key); } catch (e) {} box.remove(); };
})();
