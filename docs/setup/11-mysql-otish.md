# 11. SQLite dan MySQL ga o'tish

Hozir tizim SQLite (bitta fayl `db.sqlite3`) da ishlaydi. Doimiy ish uchun MySQL tezroq va ishonchliroq: bir vaqtda ko'p foydalanuvchi, ko'p fon vazifa va katta statistika bilan muammosiz ishlaydi.

**Ma'lumotlaringiz yo'qolmaydi:** ko'chirishdan oldin zaxira olinadi, xato bo'lsa `.env` o'zgarmaydi va tizim SQLite da ishlashda davom etadi.

## 1-qadam. MySQL ni o'rnatish

Variant A (eng oson, Windows 10/11): PowerShell ni oching va:

```
winget install Oracle.MySQL
```

Variant B: dev.mysql.com/downloads/installer dan **MySQL Installer** → *Server only* → *Development Computer*, port **3306**, *Use Strong Password Encryption*.

O'rnatishda `root` uchun parol o'ylab toping va **eslab qoling** (boshqa joyga yozib qo'ying). «Start MySQL Server at System Startup» yoqilgan bo'lsin — shunda kompyuter yoqilganda MySQL o'zi ishga tushadi.

Tekshirish: `Win+R` → `services.msc` → ro'yxatda **MySQL80** (yoki MySQL) holati *Running*, turi *Automatic* bo'lsin.

## 2-qadam. Ko'chirish

1. `stop.bat` ni ishga tushiring (tizim to'xtaydi).
2. `mysql_otish.bat` ni ikki marta bosing.
3. Savollarga javob bering: manzil (`127.0.0.1` — Enter), port (Enter), baza nomi (Enter), foydalanuvchi (Enter), **yangi baza paroli** o'ylab toping, so'ng MySQL `root` parolini kiriting. Parollar ekranda ko'rinmaydi.
4. Dastur o'zi: baza va foydalanuvchi yaratadi → SQLite zaxirasini `backups\` ga saqlaydi → jadvallarni yaratadi → ma'lumotlarni ko'chiradi → yozuvlar sonini solishtiradi → `.env` ni MySQL ga o'zgartiradi.
5. Oxirida «Hammasi mos» yozuvi chiqsa — tayyor. `run.bat` ni ishga tushiring (yoki `autostart.bat` yoqilgan bo'lsa, shunchaki kompyuterni qayta yoqing).

Baza paroli hech qayerda ochiq ko'rsatilmaydi; u faqat `.env` faylida saqlanadi (uni hech kimga yubormang).

## Avtomatik ishga tushish bilan birga

`autostart.bat` kompyuter yoqilganda avval MySQL tayyor bo'lishini kutadi (45 soniyagacha va undan ko'p marta qayta urinadi), shuning uchun MySQL xizmati *Automatic* bo'lsa, tartib o'zi to'g'ri ishlaydi.

## Orqaga qaytish (agar kerak bo'lsa)

1. `stop.bat`.
2. `.env.sqlite-<sana>.bak` faylini `.env` nomi bilan nusxalang (yoki `.env` da `DB_ENGINE=sqlite` deb yozing).
3. `run.bat`. Ko'chirishdan keyingi yangi ma'lumotlar MySQL da qolgan bo'ladi; eski ma'lumotlar `db.sqlite3` da saqlangan.

## Muammolar

- **«MySQL ga ulanib bo'lmadi»** — `services.msc` da MySQL80 ni *Start* qiling; root paroli to'g'riligini tekshiring.
- **«Qatorlar soni mos kelmadi»** — ko'chirish to'xtatiladi, `.env` o'zgarmaydi; xabarni menga yuboring.
- **Zaxira** — MySQL ga o'tgach `backup.bat` mysqldump orqali zaxira oladi (PATH da `mysqldump` bo'lishi kerak; odatda `C:\Program Files\MySQL\MySQL Server 8.x\bin`).
