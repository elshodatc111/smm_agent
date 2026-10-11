"""Boshlang'ich tasdiqlangan manbalar (butun dunyo). Manzillar (RSS) vaqt o'tishi bilan o'zgarishi mumkin:
ishlamaganini «Tekshirish» tugmasi aniqlaydi, Faktlar → Manbalar bo'limida o'zgartirish/qo'shish mumkin.
Daraja: A — rasmiy/birlamchi manba (kompaniya yoki tashkilotning o'z nashri), B — nufuzli ommaviy nashr."""
from __future__ import annotations

# (nom, sayt, rss, daraja, til, sohalar)
SOURCES = [
    # --- ijtimoiy tarmoqlar / marketing (hamma biznes uchun)
    ("Meta Newsroom", "https://about.fb.com/news/", "https://about.fb.com/news/feed/", "A", "en", ["smm"]),
    ("YouTube Official Blog", "https://blog.youtube/", "https://blog.youtube/rss/", "A", "en", ["smm", "creator"]),
    ("Social Media Examiner", "https://www.socialmediaexaminer.com/", "https://www.socialmediaexaminer.com/feed/", "B", "en", ["smm", "creator"]),
    ("Hootsuite Blog", "https://blog.hootsuite.com/", "https://blog.hootsuite.com/feed/", "B", "en", ["smm"]),
    ("Buffer Resources", "https://buffer.com/resources/", "https://buffer.com/resources/rss/", "B", "en", ["smm", "creator"]),
    ("Sprout Social Insights", "https://sproutsocial.com/insights/", "https://sproutsocial.com/insights/feed/", "B", "en", ["smm"]),
    ("Search Engine Journal", "https://www.searchenginejournal.com/", "https://www.searchenginejournal.com/feed/", "B", "en", ["smm", "business"]),
    ("Later Blog", "https://later.com/blog/", "https://later.com/blog/feed/", "B", "en", ["smm", "creator"]),
    # --- dizayn
    ("Figma Blog", "https://www.figma.com/blog/", "https://www.figma.com/blog/feed/atom.xml", "A", "en", ["design"]),
    ("Smashing Magazine", "https://www.smashingmagazine.com/", "https://www.smashingmagazine.com/feed/", "B", "en", ["design", "tech"]),
    ("Creative Bloq", "https://www.creativebloq.com/", "https://www.creativebloq.com/feeds/all", "B", "en", ["design"]),
    ("Dezeen", "https://www.dezeen.com/", "https://www.dezeen.com/feed/", "B", "en", ["design", "realestate"]),
    # --- texnologiya / IT
    ("TechCrunch", "https://techcrunch.com/", "https://techcrunch.com/feed/", "B", "en", ["tech", "business"]),
    ("The Verge", "https://www.theverge.com/", "https://www.theverge.com/rss/index.xml", "B", "en", ["tech"]),
    ("Flutter (Medium)", "https://medium.com/flutter", "https://medium.com/feed/flutter", "A", "en", ["tech"]),
    ("Google Developers Blog", "https://developers.googleblog.com/", "https://developers.googleblog.com/feeds/posts/default", "A", "en", ["tech"]),
    # --- biznes
    ("Harvard Business Review", "https://hbr.org/", "https://feeds.hbr.org/harvardbusiness", "B", "en", ["business"]),
    ("Inc.", "https://www.inc.com/", "https://www.inc.com/rss/", "B", "en", ["business"]),
    # --- ta'lim
    ("Edutopia", "https://www.edutopia.org/", "https://www.edutopia.org/rss.xml", "B", "en", ["education"]),
    ("eSchool News", "https://www.eschoolnews.com/", "https://www.eschoolnews.com/feed/", "B", "en", ["education"]),
    ("UNESCO News", "https://www.unesco.org/en/articles", "https://www.unesco.org/en/rss.xml", "A", "en", ["education"]),
    # --- ovqat
    ("Eater", "https://www.eater.com/", "https://www.eater.com/rss/index.xml", "B", "en", ["food"]),
    ("Bon Appétit", "https://www.bonappetit.com/", "https://www.bonappetit.com/feed/rss", "B", "en", ["food"]),
    # --- savdo / e-commerce / moda
    ("Shopify Blog", "https://www.shopify.com/blog", "https://www.shopify.com/blog.atom", "B", "en", ["ecommerce", "business"]),
    ("Practical Ecommerce", "https://www.practicalecommerce.com/", "https://www.practicalecommerce.com/feed", "B", "en", ["ecommerce"]),
    ("Vogue", "https://www.vogue.com/", "https://www.vogue.com/feed/rss", "B", "en", ["fashion", "beauty"]),
    # --- salomatlik / go'zallik / sport
    ("WHO News", "https://www.who.int/news", "https://www.who.int/rss-feeds/news-english.xml", "A", "en", ["health", "fitness"]),
    ("Healthline News", "https://www.healthline.com/health-news", "https://www.healthline.com/rss/health-news", "B", "en", ["health", "fitness", "beauty"]),
    ("ACE Fitness Blog", "https://www.acefitness.org/resources/everyone/blog/", "https://www.acefitness.org/resources/everyone/blog/feed/", "B", "en", ["fitness"]),
    # --- ko'chmas mulk
    ("Realtor.com News", "https://www.realtor.com/news/", "https://www.realtor.com/news/feed/", "B", "en", ["realestate"]),
]

# Biznes turi kaliti → sohalar. «smm» barcha turlarga qo'shiladi (platforma yangiliklari hamma uchun foydali).
TYPE_DOMAINS = {
    "shaxsiy_blog": ["design", "creator", "smm"], "oquv_markaz": ["education", "smm"], "restoran_kafe": ["food", "smm"],
    "onlayn_dokon": ["ecommerce", "smm"], "kiyim_dokoni": ["fashion", "ecommerce", "smm"], "xizmat_korsatish": ["business", "smm"],
    "goza_salon": ["beauty", "fashion", "smm"], "tibbiyot_klinika": ["health", "smm"], "it_kompaniya": ["tech", "business", "smm"],
    "kochmas_mulk": ["realestate", "business", "smm"], "fitnes_sport": ["fitness", "health", "smm"], "kontent_yaratuvchi": ["creator", "smm", "design"],
    "boshqa": ["business", "smm"], "kompyuter_xizmatlari": ["tech", "business", "smm"],
}


def domains_for(type_key: str | None) -> list[str]:
    return TYPE_DOMAINS.get(type_key or "", ["business", "smm"])
