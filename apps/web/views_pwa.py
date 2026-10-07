"""PWA: manifest, service worker, oflayn sahifa va o'rnatish yo'riqnomasi."""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from apps.core.settings_store import get_setting

SW_VERSION = "smm-v15"


def manifest(request):
    name = get_setting("general.system_name", "SMM Platforma")
    color = get_setting("general.brand_color", "#E11D2E")
    data = {
        "id": "/", "name": name, "short_name": (name[:12] or "SMM"), "description": "SMM boshqaruv platformasi: kalendar, nashr, tahlil, hisobotlar",
        "start_url": "/app/?source=pwa", "scope": "/", "display": "standalone", "display_override": ["standalone", "minimal-ui"], "orientation": "any",
        "background_color": "#ffffff", "theme_color": color, "lang": "uz", "dir": "ltr", "categories": ["business", "productivity"],
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Yangi kontent", "url": "/app/kalendar/yangi/", "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
            {"name": "Kalendar", "url": "/app/kalendar/", "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
            {"name": "Vazifalar", "url": "/app/vazifalar/", "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
            {"name": "Bildirishnomalar", "url": "/app/bildirishnomalar/", "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
        ],
    }
    r = HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/manifest+json")
    r["Cache-Control"] = "no-cache"
    return r


SW = """
const V='%(v)s', STATIC=V+'-static';
const SHELL=['/oflayn/','/static/favicon.svg','/static/icons/icon-192.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(STATIC).then(c=>Promise.all(SHELL.map(u=>c.add(u).catch(()=>0)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>!k.startsWith(V)).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET') return;
  const u=new URL(r.url); if(u.origin!==location.origin) return;
  if(u.pathname.startsWith('/static/')){
    e.respondWith(caches.open(STATIC).then(c=>c.match(r).then(hit=>{
      const net=fetch(r).then(res=>{if(res.ok)c.put(r,res.clone());return res}).catch(()=>hit);
      return hit||net})));
    return;
  }
  if(r.mode==='navigate'){
    e.respondWith(fetch(r).catch(()=>caches.match('/oflayn/').then(x=>x||new Response('Oflayn',{status:503}))));
    return;
  }
});
"""


def service_worker(request):
    r = HttpResponse(SW % {"v": SW_VERSION}, content_type="application/javascript")
    r["Service-Worker-Allowed"] = "/"
    r["Cache-Control"] = "no-cache"
    return r


def offline(request):
    return render(request, "offline.html", {"system_name": get_setting("general.system_name", "SMM Platforma"), "brand_color": get_setting("general.brand_color", "#E11D2E")})


@login_required
def install_help(request):
    from . import ui
    https = request.is_secure()
    host = request.get_host().split(":")[0]
    ok_local = host in ("localhost", "127.0.0.1")
    status = ("✅ Ulanish xavfsiz (HTTPS) — ilovani o'rnatish mumkin." if https else
              "✅ Bu kompyuterda (localhost) o'rnatish mumkin." if ok_local else
              "⚠ Siz hozir oddiy HTTP orqali (IP manzil) kirgansiz. Telefon brauzerlari bunday manzilga ilovani o'rnatishga ruxsat BERMAYDI. Pastdagi «HTTPS» yo'lini tanlang.")
    blocks = [
        {"type": "text", "title": "Holat", "text": status},
        {"type": "html", "title": "Kompyuterda (Chrome / Edge)", "html": "<ol><li>Manzil satrining o'ng chetidagi <b>o'rnatish</b> belgisini (⊕ yoki monitor) bosing, yoki sarlavhadagi <b>«📲 O'rnatish»</b> tugmasini.</li><li>«O'rnatish» ni tasdiqlang — ilova alohida oynada, Ish stolida va Start menyusida paydo bo'ladi.</li></ol>"},
        {"type": "html", "title": "Android telefon (Chrome)", "html": "<ol><li>Saytni Chrome'da oching (HTTPS manzil bilan).</li><li>Sarlavhadagi <b>«📲 O'rnatish»</b> tugmasi yoki ⋮ menyu → <b>«Ilovani o'rnatish»</b>.</li><li>Bosh ekranda «SMM Platforma» belgisi paydo bo'ladi, to'liq ekranda ochiladi.</li></ol>"},
        {"type": "html", "title": "iPhone / iPad (Safari)", "html": "<ol><li>Saytni <b>Safari</b>'da oching (Chrome emas).</li><li>Pastdagi <b>Ulashish</b> (⬆) tugmasi → <b>«Bosh ekranga qo'shish»</b>.</li><li>«Qo'shish» ni bosing.</li></ol>"},
        {"type": "html", "title": "HTTPS qanday olinadi (bepul, serverga ko'chirmasdan)", "html": "<p>Platforma sizning kompyuteringizda ishlaydi, shuning uchun telefon uchun xavfsiz manzil kerak. Eng oson yo'l — <b>Cloudflare Tunnel</b>:</p><ol><li>Cloudflare'da bepul hisob oching va <code>cloudflared</code> ni kompyuterga o'rnating.</li><li>Zero Trust → Networks → Tunnels → yangi tunnel yarating, <b>Public hostname</b> qo'shing (masalan <code>smm.sizningdomen.uz</code>) va xizmat sifatida <code>http://localhost:8000</code> ni kiriting.</li><li>Tunnel xizmati Windows bilan birga avtomatik ishga tushadi (o'rnatish buyrug'i shuni qiladi).</li><li><code>.env</code> faylida <code>ALLOWED_HOSTS</code> va <code>CSRF_TRUSTED_ORIGINS</code> ga shu domenni qo'shing, platformani qayta ishga tushiring.</li><li>Telefonda <code>https://smm.sizningdomen.uz</code> ni oching — endi «O'rnatish» ishlaydi.</li></ol><p class='muted'>Cloudflare Access (Zero Trust) bilan tunnelni faqat o'z elektron pochtalaringiz uchun yopib qo'ysangiz, xavfsizlik yanada oshadi. Batafsil: Yo'riqnoma → «Ilova sifatida o'rnatish».</p>"},
    ]
    return ui.page(request, "Ilova sifatida o'rnatish (PWA)", blocks, subtitle="Telefon va kompyuterga alohida ilova kabi o'rnatish")
