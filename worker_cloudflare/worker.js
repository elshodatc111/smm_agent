// SMM Platforma — Cloudflare Worker (bepul tarif doirasida).
// Vazifalar: (1) qisqa havolalar + klik hisobi (D1), (2) vaqtinchalik fayl hosting (KV, TTL bilan o'zi o'chadi),
// (3) OAuth callback yo'naltirgich (Meta/Google -> lokal server), (4) holat.
// Bog'lamalar (Bindings): KV = LINKS, D1 = DB, Secret = ADMIN_TOKEN, Var = ALLOWED_HOSTS (ixtiyoriy).
//
// D1 jadvallari (bir marta, konsolda bajaring):
//   CREATE TABLE IF NOT EXISTS clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, t INTEGER, source TEXT, device TEXT, country TEXT);
//   CREATE INDEX IF NOT EXISTS idx_clicks_t ON clicks(t);

const VERSION = "1.0";
const MIME = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", mp4: "video/mp4", mov: "video/quicktime", webp: "image/webp" };

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
}
function authorized(req, env) {
  const h = req.headers.get("authorization") || "";
  return env.ADMIN_TOKEN && h === `Bearer ${env.ADMIN_TOKEN}`;
}
function deviceOf(ua) {
  ua = (ua || "").toLowerCase();
  if (/bot|crawl|spider|preview|facebookexternalhit|telegrambot/.test(ua)) return "bot";
  if (/ipad|tablet/.test(ua)) return "tablet";
  if (/mobile|android|iphone/.test(ua)) return "mobile";
  return "desktop";
}
function sourceOf(ref) {
  try { return ref ? new URL(ref).hostname.replace(/^www\./, "") : "direct"; } catch { return "direct"; }
}
// Faqat lokal tarmoq manzillariga yo'naltiriladi (open-redirect himoyasi)
function isPrivateHost(h) {
  h = (h || "").toLowerCase();
  if (/^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(h)) return true;
  // Nuqtasiz kompyuter nomi (masalan "smm") yoki .local/.lan/.home — internetda mavjud emas, faqat ichki tarmoq
  return /^[a-z0-9][a-z0-9-]*$/.test(h) || /\.(local|lan|home|internal|localdomain)$/.test(h);
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;

    // ---- OAuth callback: /oauth/<provider>/callback?code=..&state=<base64url(JSON{b: "http://192.168.x.x:8000"})>.<nonce>
    if (path.startsWith("/oauth/") && path.endsWith("/callback")) {
      const provider = path.split("/")[2];
      const state = url.searchParams.get("state") || "";
      let target = null;
      try {
        const b64 = state.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
        const meta = JSON.parse(atob(b64));
        const u = new URL(meta.b);
        if (isPrivateHost(u.hostname)) target = u;
      } catch (e) { /* noto'g'ri state */ }
      if (!target) return new Response("Noto'g'ri yoki xavfsiz bo'lmagan yo'naltirish.", { status: 400 });
      target.pathname = `/oauth/${provider}/done/`;
      for (const [k, v] of url.searchParams) target.searchParams.set(k, v);
      return Response.redirect(target.toString(), 302);   // kod Worker'da saqlanmaydi va loglanmaydi
    }

    // ---- Vaqtinchalik fayl (KV): GET /tmp/<key>
    if (path.startsWith("/tmp/") && req.method === "GET") {
      const key = "tmp:" + path.slice(5);
      const { value, metadata } = await env.LINKS.getWithMetadata(key, { type: "arrayBuffer" });
      if (!value) return new Response("Topilmadi", { status: 404 });
      const ext = path.split(".").pop().toLowerCase();
      return new Response(value, { headers: { "content-type": MIME[ext] || "application/octet-stream", "cache-control": "no-store" } });
    }

    // ---- Admin API
    if (path.startsWith("/admin/")) {
      if (!authorized(req, env)) return json({ error: "unauthorized" }, 401);
      if (path === "/admin/status") {
        const day = Math.floor(Date.now() / 86400000) * 86400;
        let today = 0;
        try { today = (await env.DB.prepare("SELECT COUNT(*) AS n FROM clicks WHERE t >= ?").bind(day).first()).n; } catch (e) {}
        return json({ ok: true, version: VERSION, clicks_today: today });
      }
      if (path.startsWith("/admin/links/")) {
        const slug = path.split("/")[3];
        if (req.method === "PUT") { await env.LINKS.put("link:" + slug, JSON.stringify(await req.json())); return json({ ok: true }); }
        if (req.method === "DELETE") { await env.LINKS.delete("link:" + slug); return json({ ok: true }); }
      }
      if (path.startsWith("/admin/tmp/") && req.method === "PUT") {
        const key = "tmp:" + path.slice(11);
        const ttl = Math.max(60, parseInt(url.searchParams.get("ttl") || "10800"));
        const body = await req.arrayBuffer();
        if (body.byteLength > 24 * 1024 * 1024) return json({ error: "too_large" }, 413);
        await env.LINKS.put(key, body, { expirationTtl: ttl });
        return json({ ok: true });
      }
      if (path.startsWith("/admin/tmp/") && req.method === "DELETE") {
        await env.LINKS.delete("tmp:" + path.slice(11)); return json({ ok: true });
      }
      if (path === "/admin/clicks") {
        const after = parseInt(url.searchParams.get("after") || "0");
        const rs = await env.DB.prepare("SELECT id, slug, t, source, device, country FROM clicks WHERE id > ? ORDER BY id LIMIT 500").bind(after).all();
        return json({ clicks: rs.results });
      }
      return json({ error: "not_found" }, 404);
    }

    // ---- Qisqa havola: GET /<slug>
    const slug = path.slice(1);
    if (slug && /^[a-z0-9_-]{1,40}$/i.test(slug)) {
      const raw = await env.LINKS.get("link:" + slug);
      if (!raw) return new Response("Havola topilmadi", { status: 404 });
      const link = JSON.parse(raw);
      if (link.enabled === false || (link.exp && link.exp < Date.now() / 1000)) return new Response("Havola faol emas", { status: 410 });
      const ua = req.headers.get("user-agent");
      const dev = deviceOf(ua);
      if (dev !== "bot") {
        const row = [slug, Math.floor(Date.now() / 1000), sourceOf(req.headers.get("referer")), dev, (req.cf && req.cf.country) || ""];
        ctx.waitUntil(env.DB.prepare("INSERT INTO clicks (slug, t, source, device, country) VALUES (?,?,?,?,?)").bind(...row).run().catch(() => {}));
      }
      return Response.redirect(link.url, 302);   // IP saqlanmaydi
    }
    return new Response("SMM Platforma Worker", { status: 200 });
  },
};
