# 9. Zaxira nusxa va tiklash

## Nima zaxiralanadi

Har kecha avtomatik (Toshkent vaqti bilan ~03:30, server yoniq bo'lsa) `backups\` papkasiga: ma'lumotlar bazasi dumpi (`smm_YYYYMMDD_HHMM.sql.gz`, `mysqldump` orqali) va `.env` nusxasi (`env_….backup`). Standart bo'yicha 14 kunlik nusxalar saqlanadi (*Sozlamalar → Zaxira*). Qo'lda: `backup.bat` yoki «Tizim holati → Zaxira nusxa olish».

## Eng muhim: FERNET kalit

Bazadagi barcha maxfiy ma'lumotlar (ulanish tokenlari, API kalitlar, Telethon sessiyalari) `.env` dagi `FERNET_KEYS` bilan shifrlangan. Baza zaxirasi bu kalitsiz **foydasiz**. Shuning uchun:

1. `.env` faylini (yoki kamida `FERNET_KEYS` qatorini) **bazadan alohida joyda** saqlang (flesh, parol menejeri).
2. `backups\` papkasini boshqa diskka/bulutga muntazam nusxalang (tashqi disk yoki ofis NAS). Server diski buzilsa, faqat shu papka va kalit sizni qutqaradi.
3. Fayllar (yuklangan media) `media_store\` da — ularni ham nusxalang.

Kalitni almashtirish (rotatsiya): `.env` da `FERNET_KEYS=YANGI,ESKI` — birinchisi shifrlaydi, hammasi ochadi.

## Tiklash (yangi kompyuterda yoki avariyadan keyin)

1. Loyihani o'rnating (0-bo'lim), lekin `.env` ni **zaxiradagi** nusxadan qo'ying (kalitlar bir xil bo'lsin).
2. MySQL'da bo'sh baza yarating (1-bo'lim).
3. Dump'ni oching va qaytaring (PowerShell/CMD, loyiha papkasida):
   `.venv\Scripts\python -c "import gzip,shutil;shutil.copyfileobj(gzip.open('backups/smm_YYYYMMDD_HHMM.sql.gz'),open('dump.sql','wb'))"`
   `mysql -u smm -p smm_platform < dump.sql`
4. `media_store\` ni joyiga qo'ying.
5. `run.bat`. Ulanishlar qayta tekshiriladi; muddati o'tgan tokenlar «Qayta ulash» talab qiladi.

## Qo'shimcha xavfsizlik

- **Diqqat:** `backups\` ichidagi `env_….backup` fayli shifrlash kalitini o'z ichiga oladi. Shu papkani boshqa joyga (bulut, tashqi disk) nusxalasangiz, u yerda baza ham, kalit ham bo'ladi — papkani **shifrlangan arxiv (parolli zip/7z)** yoki shifrlangan diskda saqlang.

- `.env` va `backups\` ni hech qachon internetga/umumiy papkaga qo'ymang.
- Administrator parolini kuchli qiling; xodim ketsa darhol foydalanuvchini o'chiring (Foydalanuvchilar).
- Audit jurnali (Admin) kim nima qilganini saqlaydi (o'chirib bo'lmaydi).
