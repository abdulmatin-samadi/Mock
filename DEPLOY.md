# DreamZone'ni internetga chiqarish

**Backend** (Django, baza, AI) → **Render**.  **Frontend** (CSS, JS, rasmlar) → **Netlify**.
Barcha sozlamalar tayyor: `render.yaml` va `netlify.toml`. Siz faqat tugmalarni bosasiz.

> Tartib muhim: **avval Render**, keyin Netlify.

---

## 1. Render — backend (≈10 daqiqa)

1. Shu tugmani bosing: [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/abdulmatin-samadi/Mock)
   — yoki **render.com → New → Blueprint →** `abdulmatin-samadi/Mock` repozitoriyini tanlang.
2. Render 3 ta qiymat so'raydi:

   | Nomi | Nima yoziladi |
   |---|---|
   | `ADMIN_EMAIL` | admin panelga kiradigan email, masalan `admin@dreamzone.uz` |
   | `ADMIN_PASSWORD` | kuchli parol (kamida 10 belgi) |
   | `AI_API_KEY` | Gemini kaliti — https://aistudio.google.com/apikey |

3. **Apply** (yoki **Deploy Blueprint**) ni bosing. Render server va PostgreSQL bazani yaratadi.
4. Build tugashini kuting (5–10 daqiqa). Holat **Live** bo'lganda server manzili ko'rinadi, masalan
   `https://dreamzone-samadi-api.onrender.com` — uni nusxalab oling.
5. Tekshiring: shu manzilga `/accounts/login/` qo'shib oching — login sahifasi chiqishi kerak.

## 2. Netlify — frontend (≈3 daqiqa)

1. Shu tugmani bosing: [![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/abdulmatin-samadi/Mock)
   — yoki **app.netlify.com → Add new site → Import an existing project → GitHub →** `Mock`.
2. Sozlamalar `netlify.toml` dan o'zi olinadi (Base directory `frontend`, Publish `public`). **Deploy** ni bosing.
3. **Faqat Render manzili `https://dreamzone-samadi-api.onrender.com` dan farq qilsa:**
   Netlify → **Site configuration → Environment variables → Add** → `BACKEND_URL` = Render manzilingiz →
   **Deploys → Trigger deploy**.
4. Netlify manzilini oching (masalan `https://dreamzone-xxxx.netlify.app`) — sayt tayyor.
   Admin panel: `…netlify.app/admin/` → 1-qadamdagi email va parol.

---

## Google orqali kirish (ixtiyoriy, ≈10 daqiqa)
Kirish va ro'yxatdan o'tish sahifalarida **«Google bilan davom etish»** tugmasi faqat quyidagi ikki kalit
qo'shilgandan keyin chiqadi.
1. console.cloud.google.com → yuqoridan loyiha tanlang yoki **New project** (`DreamZone`).
2. **APIs & Services → OAuth consent screen** → *External* → ilova nomi `DreamZone`, email'ingiz → Save.
   **Audience / Publishing status** → **Publish app** (aks holda faqat test foydalanuvchilar kira oladi).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → turi **Web application**.
   - *Authorized JavaScript origins*: `https://mockcefr.netlify.app`
   - *Authorized redirect URIs*: `https://mockcefr.netlify.app/accounts/google/callback/`
   → **Create**. Ko'rsatilgan **Client ID** va **Client secret** ni nusxalang.
4. Render → `dreamzone-samadi-api` → **Environment** → qo'shing:
   `GOOGLE_CLIENT_ID=…`, `GOOGLE_CLIENT_SECRET=…` → **Save Changes**.
   (Sayt manzili boshqa bo'lsa, `GOOGLE_REDIRECT_URI` ni ham o'sha manzilga moslang.)

Google'dan kelgan email bilan hisob bo'lsa — o'sha hisobga kiradi; bo'lmasa yangi o'quvchi hisobi ochiladi.

## Til
Sayt **o'zbekcha** ochiladi; yuqoridagi **UZ / EN** tugmasi bilan inglizchaga o'tadi. Admin panel inglizcha.
AI fikr-mulohaza tilini (o'zbekcha / inglizcha) har bir o'quvchi **Profil** sahifasida tanlaydi.

## Keyinchalik yangilash
GitHub'ga yangi kod yuklansa, Render ham, Netlify ham **o'zi qayta joylaydi**.

## Bilishingiz kerak
- **Birinchi ochilish sekin.** Bepul Render server 15 daqiqa ishlatilmasa uxlaydi; uyg'onishi 30–60 soniya.
  Netlify shu paytda xato ko'rsatsa — 1 daqiqadan keyin sahifani yangilang.
- **Yuklangan fayllar o'chadi** (Listening audio, rasmlar, ovoz yozuvlari) — bepul Render diski har qayta
  ishga tushganda tozalanadi. Saqlash uchun **Cloudflare R2** ulang (10 GB bepul):
  1. dash.cloudflare.com → **R2 Object Storage** → (karta so'raladi, 10 GB gacha pul yechilmaydi) →
     **Create bucket** → nomi `dreamzone-media` → Create. Bucket **yopiq** qoladi.
  2. R2 → **Manage R2 API Tokens** → **Create API token** → ruxsat **Object Read & Write**, faqat shu bucket →
     Create. Ko'rsatilgan **Access Key ID**, **Secret Access Key** va **S3 endpoint**
     (`https://<account-id>.r2.cloudflarestorage.com`) ni nusxalab oling.
  3. Render → `dreamzone-samadi-api` → **Environment** → qo'shing:
     `USE_S3=True`, `AWS_STORAGE_BUCKET_NAME=dreamzone-media`, `AWS_ACCESS_KEY_ID=…`,
     `AWS_SECRET_ACCESS_KEY=…`, `AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`,
     `AWS_S3_REGION_NAME=auto` → **Save Changes** (server o'zi qayta ishga tushadi).
  4. Avval yuklangan audio va rasmlarni qaytadan yuklang.
- **Bepul PostgreSQL** Render'da ma'lum muddatdan keyin o'chiriladi — Render'dagi ogohlantirishni kuzating.
- **Mocklar bo'sh boshlanadi.** Yangi bazada mock yo'q — admin paneldagi ⚡ Quick entry bilan qo'shasiz.
- **Kalitlar GitHub'da emas.** `AI_API_KEY` va admin paroli faqat Render sozlamalarida saqlanadi.
