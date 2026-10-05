# 10. Muammolarni hal qilish

Birinchi qadam har doim: **Tizim holati** sahifasi — qizil bandlar va «Tavsiyalar» ro'yxati. Ikkinchi: `.venv\Scripts\python manage.py doctor`.

| Alomat | Sabab va yechim |
|---|---|
| `run.bat` darhol yopiladi | Oynada xabarni o'qing. Odatda Python PATH da yo'q yoki MySQL ishlamayapti. |
| Sahifa ochilmaydi (boshqa kompyuterdan) | Firewall 8000-port; server IP o'zgargan; `.env` → `PUBLIC_BASE_URL`. |
| Nashr/yig'ish bajarilmayapti | «Tizim holati»: Worker javob bermayapti → `run.bat` oynasi yopilgan. Avtostartni yoqing. |
| Instagram «Token tugayapti» | Ulanishlar → hisob → «Qayta ulash (OAuth)». |
| YouTube har hafta uziladi | OAuth ilova hali *Testing*: Production'ga o'tkazing (3-bo'lim). |
| YouTube video «private» bo'lib chiqdi | Tasdiqlanmagan loyiha cheklovi: API audit so'rang (3-bo'lim). |
| «Kunlik kvota tugadi» | YouTube yuklash ~6/kun; tizim ertaga qoldiradi. Tichiy okean yarim tunida yangilanadi. |
| Telethon «cooldown» | FloodWait yoki ketma-ket xato: ko'rsatilgan vaqt o'tguncha kuting; kunlik limitni kamaytiring. |
| ScrapeCreators o'chib qoldi | Kredit chegarasi yoki kunlik limit. Provayderlar sahifasida sababi yozilgan. |
| AI «hamma provayder band» | Kalit qo'shing yoki limit tiklanishini kuting; Claude yoqilmagan bo'lsa pullik zaxira yo'q. |
| Matn o'zbekcha emas chiqdi | Tizim o'zi qayta so'raydi; takroran bo'lsa brend xotirasiga «Faqat o'zbek (lotin)» ko'rsatmasini qo'shing. |
| `FERNET`/«decrypt» xatosi | `.env` dagi kalit bazaga mos emas — to'g'ri `.env` ni qaytaring (9-bo'lim). |
| Kontent «To'xtatildi» | Kontent sahifasida «Qoidalar natijasi»dagi sababni tuzating (masalan faktlar bilan mos kelmaydigan raqam). |

## Loglar

`logs\app.log` (tizim), `logs\serve.out.log`, `logs\worker.out.log`. Loglarda parol, token va kalitlar maskalanadi, lekin baribir uchinchi shaxsga yuborishdan oldin tekshiring.

## Yordam so'rashda nimani yuborish kerak

`doctor` natijasi, «Tizim holati» skrinshoti va `logs\worker.out.log` oxirgi 50 qatori. `.env` faylini **yubormang**.
