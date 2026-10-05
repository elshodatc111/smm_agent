/* PWA: service worker + "Ilovani o'rnatish" tugmasi (Android/Chrome/Edge) + iOS yo'riqnomasi. */
(function () {
  var standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {}); });
  }
  var btn = document.getElementById('pwaInstall'); if (!btn || standalone) return;
  var ev = null, ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  window.addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); ev = e; btn.style.display = ''; });
  window.addEventListener('appinstalled', function () { btn.style.display = 'none'; ev = null; });
  if (ios) btn.style.display = '';
  btn.addEventListener('click', function () {
    if (ev) { ev.prompt(); ev.userChoice.finally(function () { ev = null; btn.style.display = 'none'; }); }
    else location.href = '/ilova/';
  });
})();
