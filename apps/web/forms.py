from django import forms

from apps.businesses.models import Business
from apps.connections.models import Competitor, TelegramBot, TelegramSession
from apps.content.models import ContentItem


BUSINESS_UZ = {
    "name": ("Biznes nomi", "Mijozlar biladigan rasmiy nom.", "Masalan: ATKO o'quv markazi"),
    "template": ("Soha shabloni", "Tanlansa, tavsiya etilgan kontent ustunlari, hashtaglar va rejalar avtomatik tayyorlanadi.", ""),
    "industry": ("Soha", "", "Ta'lim — o'quv markaz"),
    "region": ("Hudud", "Qaysi shahar/tumanlarga xizmat ko'rsatasiz.", "Toshkent shahri, Chilonzor tumani"),
    "languages": ("Kontent tillari", "Vergul bilan: uz, ru, en", "uz, ru"),
    "description": ("Biznes haqida", "AI shu matndan brend ovozini o'rganadi. 4-6 gap: kim siz, nimasi bilan ajralib turasiz, necha yildan beri, natijalar.", ""),
    "products": ("Xizmat / mahsulotlar", "Har qatorda bitta kurs: nomi, davomiyligi, formati.", "Ingliz tili (IELTS) — 6 oy\nMatematika (abituriyent) — 8 oy\nIT: Python — 5 oy"),
    "price_range": ("Narx oralig'i", "", "Oyiga 400 000 – 900 000 so'm"),
    "audience": ("Maqsadli auditoriya", "Kimga sotasiz: yoshi, qiziqishi, ehtiyoji. Ota-onalar va o'quvchilar alohida yozilsin.", "16–24 yoshli abituriyentlar; 30–45 yoshli ota-onalar"),
    "main_goal": ("Asosiy maqsad", "Hisobotlar va tavsiyalar shunga qarab tuziladi.", ""),
    "monthly_ad_budget": ("Oylik reklama byudjeti", "Bo'sh qoldirsangiz 0 bo'ladi.", "5000000"),
    "currency": ("Valyuta", "UZS yoki USD", "UZS"),
    "avg_check": ("O'rtacha chek (bir o'quvchi)", "Bir o'quvchidan oylik tushum.", "600000"),
    "lead_to_sale": ("Lead → o'quvchi konversiyasi", "0.2 = har 5 ta murojaatdan 1 tasi yoziladi.", "0.2"),
    "margin": ("Foyda marjasi", "0.35 = 35%. Bilmasangiz bo'sh qoldiring.", "0.35"),
    "contact_info": ("Aloqa ma'lumotlari", "Postlarda ishlatiladi: telefon, manzil, Telegram, ish vaqti.", "Tel: +998 90 000 00 00\nManzil: Chilonzor 7-mavze\nTelegram: @atko_admin\nIsh vaqti: 09:00–20:00"),
    "logo": ("Logotip", "PNG yoki JPG, kvadrat bo'lsa yaxshi.", ""),
}


class BusinessForm(forms.ModelForm):
    facts_text = forms.CharField(label="Aniq faktlar (Content Rules «haqiqiylik» uchun)", required=False, widget=forms.Textarea(attrs={"rows": 4}),
                                 help_text="Har qatorda: kalit = qiymat. Masalan: telefon = +998 90 123 45 67 | narx = 450 000 so'm | manzil = Chilonzor 7")

    class Meta:
        model = Business
        fields = ["name", "template", "industry", "region", "languages", "description", "products", "price_range", "audience",
                  "main_goal", "monthly_ad_budget", "currency", "avg_check", "lead_to_sale", "margin", "contact_info", "logo"]
        widgets = {k: forms.Textarea(attrs={"rows": 3}) for k in ("description", "products", "audience", "contact_info")}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ("monthly_ad_budget", "avg_check", "lead_to_sale", "margin"):
            self.fields[f].required = False
        for f, (label, hint, ph) in BUSINESS_UZ.items():
            if f in self.fields:
                self.fields[f].label = label
                if hint:
                    self.fields[f].help_text = hint
                if ph:
                    self.fields[f].widget.attrs["placeholder"] = ph
        if self.instance.pk and self.instance.facts:
            self.fields["facts_text"].initial = "\n".join(f"{k} = {v}" for k, v in self.instance.facts.items())

    def clean_facts_text(self):
        out = {}
        for line in self.cleaned_data["facts_text"].splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def clean(self):
        d = super().clean()
        for f, default in (("monthly_ad_budget", 0), ("avg_check", 0), ("lead_to_sale", 0.2)):
            if d.get(f) in (None, ""):
                d[f] = default
        return d

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.facts = self.cleaned_data.get("facts_text") or {}
        if commit:
            obj.save()
        return obj


class BrandForm(forms.Form):
    content = forms.CharField(label="Brend xotirasi (AI uchun ko'rsatma)", widget=forms.Textarea(attrs={"rows": 14}))
    note = forms.CharField(label="Izoh", required=False, max_length=200)


class TelegramChannelForm(forms.Form):
    name = forms.CharField(label="Nomi", max_length=160)
    channel = forms.CharField(label="Kanal (@username yoki -100…)", max_length=120)
    bot = forms.ModelChoiceField(label="Bot (mavjud)", queryset=TelegramBot.objects.filter(active=True), required=False)
    new_bot_name = forms.CharField(label="Yoki yangi bot nomi", required=False)
    new_bot_token = forms.CharField(label="Yangi bot tokeni", required=False, widget=forms.PasswordInput(render_value=False),
                                    help_text="@BotFather bergan token. Bazada shifrlanadi.")
    tg_session = forms.ModelChoiceField(label="Telethon sessiyasi (statistika uchun, ixtiyoriy)", queryset=TelegramSession.objects.filter(active=True), required=False)


class CompetitorForm(forms.ModelForm):
    class Meta:
        model = Competitor
        fields = ["platform", "handle", "name", "url", "note"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f, (label, hint, ph) in {
            "platform": ("Tarmoq", "Raqobatchi qaysi tarmoqda kuzatiladi. Bir raqobatchi uchun har tarmoqni alohida qo'shing.", ""),
            "handle": ("Foydalanuvchi nomi (handle)", "@ belgisiz, havolasiz — faqat nomi. Telegram: kanal nomi (masalan: ielts_uz). Instagram: akkaunt nomi (masalan: ielts.center). YouTube: @kanal nomi.", "ielts_uz"),
            "name": ("Ko'rinadigan nom", "Ro'yxatda va hisobotlarda chiqadigan nom (ixtiyoriy).", "Masalan: IELTS Center"),
            "url": ("Havola", "Sahifa havolasi (ixtiyoriy).", "https://t.me/ielts_uz"),
            "note": ("Izoh", "Nega kuzatyapsiz: qaysi kuchli tomoni bor, qaysi kurslari bilan raqobat qiladi.", "Narxlari bizdan past, Instagram'da kuchli"),
        }.items():
            self.fields[f].label = label
            self.fields[f].help_text = hint
            if ph:
                self.fields[f].widget.attrs["placeholder"] = ph


ALLOWED_TYPES = {"telegram": ["text", "image", "video", "album"], "instagram": ["image", "carousel", "reel", "story"],
                 "youtube": ["video", "short"]}


class ContentForm(forms.ModelForm):
    scheduled_at = forms.DateTimeField(label="Nashr vaqti (Toshkent vaqti)", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                       input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    targets = forms.MultipleChoiceField(label="Qayerga nashr qilinadi", required=False, widget=forms.CheckboxSelectMultiple)
    yt_title = forms.CharField(label="YouTube sarlavhasi (≤100 belgi)", required=False, max_length=100)
    yt_tags = forms.CharField(label="YouTube teglari (vergul bilan)", required=False)
    yt_privacy = forms.ChoiceField(label="YouTube ko'rinishi", required=False, choices=[("public", "Hamma uchun"), ("unlisted", "Havola orqali"), ("private", "Faqat men")])
    media_size = forms.ChoiceField(label="Media o'lchami (rasm/video)", required=False, choices=[])
    fit_mode = forms.ChoiceField(label="Moslash usuli", required=False, choices=list(__import__("apps.content.mediafit", fromlist=["FIT_MODES"]).FIT_MODES.items()))
    due_at = forms.DateTimeField(label="Vazifa muddati (Toshkent vaqti)", required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                                 input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    auto_time = forms.BooleanField(label="⚡ Vaqtni tizim o'zi tanlasin (eng yaxshi bo'sh vaqt)", required=False)
    crop_x = forms.FloatField(required=False, min_value=0, max_value=1, widget=forms.HiddenInput)
    crop_y = forms.FloatField(required=False, min_value=0, max_value=1, widget=forms.HiddenInput)
    crop_zoom = forms.FloatField(required=False, min_value=1, max_value=4, widget=forms.HiddenInput)
    music_source = forms.CharField(label="Musiqa / audio manbasi", required=False, max_length=200,
                                   widget=forms.TextInput(attrs={"placeholder": "Masalan: CapCut bepul kutubxona, o'z ovozim, litsenziyali"}))
    tg_buttons = forms.CharField(label="Telegram tugmalari (har qatorda: Matn | https://havola)", required=False,
                                 widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ro'yxatdan o'tish | https://example.com"}))

    class Meta:
        model = ContentItem
        fields = ["title", "text", "media_type", "scheduled_at", "goal", "hook_idea", "cta", "notes", "assignee", "brief", "due_at"]
        labels = {"title": "Sarlavha (ichki nom)", "text": "Matn / caption (nashrda ko'rinadigan matn)", "media_type": "Post turi",
                  "goal": "Maqsad (masalan: ro'yxatdan o'tish)", "hook_idea": "Hook g'oyasi (birinchi jumla)", "cta": "CTA (chaqiriq)",
                  "notes": "Ichki izoh (nashrga chiqmaydi)", "assignee": "Mas'ul (dizayner/kontent-maker)", "brief": "Topshiriq (mas'ulga vazifa matni)"}
        widgets = {"text": forms.Textarea(attrs={"rows": 10, "placeholder": "Postning to'liq matni. #hashtag larni ham shu yerga yozing."}),
                   "notes": forms.Textarea(attrs={"rows": 2}), "brief": forms.Textarea(attrs={"rows": 3, "placeholder": "Masalan: 3 ta slayd, qizil fon, logotip pastda"})}

    def __init__(self, *a, business=None, accounts=None, **kw):
        super().__init__(*a, **kw)
        self.account_platforms = {str(x.pk): x.platform for x in (accounts or [])}
        self.fields["targets"].choices = [(str(x.pk), str(x)) for x in (accounts or [])]
        from apps.content.mediafit import size_choices
        self.fields["media_size"].choices = size_choices()
        self.fields["media_size"].initial = "orig"
        if self.instance.pk:
            self.fields["targets"].initial = [str(t.account_id) for t in self.instance.targets.all()]
            o = self.instance.options or {}
            self.fields["yt_title"].initial = o.get("title", "")
            self.fields["yt_tags"].initial = ", ".join(o.get("tags", []) or [])
            self.fields["yt_privacy"].initial = o.get("privacy", "public")
            self.fields["media_size"].initial = o.get("media_size", "orig")
            self.fields["fit_mode"].initial = o.get("fit_mode", "pad")
            self.fields["music_source"].initial = o.get("music_source", "")
            c = o.get("crop") or {}
            self.fields["crop_x"].initial, self.fields["crop_y"].initial, self.fields["crop_zoom"].initial = c.get("x", 0.5), c.get("y", 0.5), c.get("z", 1)
            self.fields["tg_buttons"].initial = "\n".join(f"{b.get('text', '')} | {b.get('url', '')}" for row in (o.get("buttons") or []) for b in row)
        for f in ("goal", "hook_idea", "cta", "notes", "assignee", "title", "brief", "due_at"):
            if f in self.fields:
                self.fields[f].required = False

    def clean(self):
        d = super().clean()
        mt = d.get("media_type")
        for pk in d.get("targets") or []:
            plat = self.account_platforms.get(str(pk))
            if plat and mt and mt not in ALLOWED_TYPES.get(plat, []):
                names = {"text": "Matn", "image": "Rasm", "video": "Video", "album": "Albom", "reel": "Reels", "short": "Shorts", "story": "Stories", "carousel": "Karusel"}
                ok = ", ".join(names[t] for t in ALLOWED_TYPES[plat])
                self.add_error("media_type", f"{plat.capitalize()} uchun «{names.get(mt, mt)}» turi mumkin emas. Mumkin: {ok}.")
                break
        return d

    def clean_tg_buttons(self):
        rows = []
        for line in (self.cleaned_data.get("tg_buttons") or "").splitlines():
            if not line.strip():
                continue
            txt, _, url = line.partition("|")
            txt, url = txt.strip(), url.strip()
            if not txt or not url.startswith(("http://", "https://", "tg://", "https://t.me")):
                raise forms.ValidationError(f"Noto'g'ri qator: «{line.strip()}». Format: Matn | https://havola")
            rows.append([{"text": txt[:64], "url": url}])
        self._tg_rows = rows
        return self.cleaned_data.get("tg_buttons")

    def options_from_cleaned(self, base: dict | None = None) -> dict:
        o = dict(base or {})
        d = self.cleaned_data
        for k, v in (("title", (d.get("yt_title") or "").strip()), ("privacy", d.get("yt_privacy") or ""),
                     ("tags", [t.strip() for t in (d.get("yt_tags") or "").split(",") if t.strip()]),
                     ("buttons", getattr(self, "_tg_rows", [])), ("music_source", (d.get("music_source") or "").strip()),
                     ("media_size", d.get("media_size") if d.get("media_size") not in (None, "", "orig") else ""),
                     ("fit_mode", d.get("fit_mode") if d.get("media_size") not in (None, "", "orig") else "")):
            if v:
                o[k] = v
            else:
                o.pop(k, None)
        if d.get("media_size") not in (None, "", "orig") and any(d.get(k) is not None for k in ("crop_x", "crop_y", "crop_zoom")):
            o["crop"] = {"x": d.get("crop_x") if d.get("crop_x") is not None else 0.5, "y": d.get("crop_y") if d.get("crop_y") is not None else 0.5,
                         "z": d.get("crop_zoom") or 1}
        else:
            o.pop("crop", None)
        return o


class AssetForm(forms.Form):
    file = forms.FileField(label="Fayl (rasm/video)")


class SettingsForm(forms.Form):
    """Dinamik: maydonlar view'da qo'shiladi."""
