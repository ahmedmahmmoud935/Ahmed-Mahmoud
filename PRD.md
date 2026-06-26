# PRD — ViralPX Portfolio Platform

> **نسخة نهائية** · مصدر: مراجعة الكود الفعلي للمشروع
> **آخر تحديث:** 2026
> **اللغة:** عربي / English (الكود ومحتوى المنصة)

---

## فهرس المحتويات
1. [الملخص التنفيذي](#1-الملخص-التنفيذي)
2. [الأهداف](#2-الأهداف)
3. [الأدوار والمستخدمون](#3-الأدوار-والمستخدمون)
4. [التقنيات المستخدمة (Tech Stack)](#4-التقنيات-المستخدمة-tech-stack)
5. [الفلسفة المعمارية (Programming Approach)](#5-الفلسفة-المعمارية-programming-approach)
6. [الميزات الأساسية](#6-الميزات-الأساسية)
7. [نموذج البيانات (Data Model)](#7-نموذج-البيانات-data-model)
8. [SEO الآلي](#8-seo-الآلي)
9. [النشر (Deployment Pipeline)](#9-النشر-deployment-pipeline)
10. [الأمان (Security)](#10-الأمان-security)
11. [الحدود الحالية والتوصيات المستقبلية](#11-الحدود-الحالية-والتوصيات-المستقبلية)
12. [مؤشرات الأداء (KPIs)](#12-مؤشرات-الأداء-kpis)

---

## 1. الملخص التنفيذي

**ViralPX** عبارة عن منصة SaaS متعددة المستأجرين (multi-tenant) لإنشاء بورتفوليوهات احترافية للمصممين والمصورين والمبدعين، مع لوحة تحكم سهلة وثيمات قابلة للتخصيص ونظام مقالات/مدونة مدمج، بالإضافة إلى Landing Page تسويقية لاكتساب العملاء.

كل عميل يحصل على:
- بورتفوليو خاص على `/<username>` أو دومين مخصص
- لوحة تحكم كاملة بدون كتابة كود
- نظام مقالات لتعزيز الـ SEO
- 5+ ثيمات وتخصيص لا محدود

---

## 2. الأهداف

| # | الهدف |
|---|------|
| G1 | تمكين أي شخص من امتلاك بورتفوليو احترافي خلال دقائق بدون كتابة كود |
| G2 | دعم اللغتين العربية والإنجليزية مع RTL/LTR تلقائي |
| G3 | تخصيص كامل (ثيمات متعددة، ألوان، خطوط، ترتيب أقسام، شريط علوي/سفلي) |
| G4 | SEO آلي بالكامل (SSR meta, OG images, JSON-LD, hreflang) |
| G5 | نظام مقالات لتعزيز الـ SEO وعرض الخبرات |
| G6 | إدارة مركزية للعملاء (Owner Panel) مع تحكم في المساحة والدومينات |
| G7 | أداء عالٍ على الموبايل (60fps scroll, lazy loading, no FOUC) |

---

## 3. الأدوار والمستخدمون

| الدور | الوصف | الواجهة | المسار |
|------|------|--------|--------|
| **Visitor** | زائر عام يتصفح المحتوى | عرض عام | `/`, `/<username>`, `/articles` |
| **Client** | عميل يملك بورتفوليو ويديره | لوحة تحكم العميل | `/admin` |
| **Owner** | المالك (إنت) يدير اللاندنج والعملاء | لوحة المالك | `/owner` |

---

## 4. التقنيات المستخدمة (Tech Stack)

### 🖥️ Backend
| التقنية | الاستخدام |
|---------|-----------|
| **Python 3** | لغة السيرفر |
| **Flask** | إطار العمل (web framework) |
| **Gunicorn** | WSGI server للإنتاج (2 workers) |
| **SQLite** | قاعدة البيانات (ملف واحد) |
| **Pillow (PIL)** | توليد صور OG ديناميكية |
| **Resend API** | إرسال البريد الإلكتروني |

### 🎨 Frontend
| التقنية | الاستخدام |
|---------|-----------|
| **HTML5 / CSS3 / Vanilla JavaScript** | بدون أي فريموورك (لا React/Vue) |
| **Font Awesome** | الأيقونات |
| **Google Fonts** (Cairo, Montserrat, Bebas Neue, Playfair Display, Inter) | الخطوط |
| **CSS Variables** | نظام الثيمات الديناميكي |
| **contenteditable + execCommand** | محرر النصوص الغني للمقالات |
| **IntersectionObserver** | تأثيرات الظهور عند الـ scroll |

### ☁️ الاستضافة والبنية التحتية
| التقنية | الاستخدام |
|---------|-----------|
| **Render** | استضافة السيرفر |
| **Persistent Disk (5GB)** | تخزين دائم لـ `/var/data` |
| **Cloudflare DNS** | إدارة النطاقات المخصصة |
| **Custom Domains على Render** | كل عميل يقدر يربط دومين خاص |

### ⚙️ النشر والإعدادات
- `render.yaml` — Blueprint للنشر
- `Procfile` — أمر التشغيل
- `requirements.txt` — تبعيات Python
- **متغيرات بيئة:** `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS`, `RESEND_API_KEY`, `RENDER=true`

---

## 5. الفلسفة المعمارية (Programming Approach)

### A. Server-Side Rendering (SSR) + Client Hydration
- HTML يُحقن فيه `<meta>` و `<title>` و JSON-LD من السيرفر **قبل** الإرسال (للـ SEO).
- المحتوى يُجلب ويُعرض client-side عبر `fetch` + DOM manipulation.
- **النتيجة:** SEO ممتاز + تجربة SPA سلسة + سرعة عالية.

### B. Single File per Page (Vanilla Approach)
- كل صفحة HTML مستقلة: `index.html`, `landing.html`, `admin.html`, `owner.html`, `articles.html`
- CSS و JS مدمجين داخل نفس الملف (`<style>` + `<script>`)
- **السبب:** تبسيط، لا build step، نشر فوري، performance ممتاز، حجم تحميل أقل.

### C. Settings as JSON
- إعدادات كل عميل تُخزن في جدول `settings` (key/value JSON).
- يقبل **أي مفتاح** بدون تعديل سيرفر — مرونة كاملة (`mobile_bar`, `navbar_links`, `colors`, إلخ).

### D. Reserved Paths
مسارات محجوزة لا يمكن أن تكون أسماء مستخدمين:
```
admin, owner, api, uploads, u, articles, og-image,
editor, testimonial, landing, static, assets, public,
robots.txt, sitemap.xml, llms.txt, favicon.ico
```

### E. Theme System (Data Attributes)
```html
<body data-theme="kinetic" data-design="modern" data-anim="fade-up">
```
الثيمات المتاحة: **Modern, Editorial, Minimal, Creative, Cinema, Corporate, Kinetic**
- CSS Variables يتم تحديثها من JS عند تغيير الثيم.

### F. Mobile-First Defensive CSS
- كل عناصر الموبايل (`drawer`, `bottom-bar`, `burger`) **`display:none` بشكل افتراضي**
- تُفعَّل فقط داخل `@media(max-width:600px)` — لمنع تسرّبها للديسكتوب.

### G. Multi-Tenancy via `user_id`
- كل جدول فيه `user_id` للفصل بين العملاء.
- `LANDING_ARTICLES_UID = 0` لمحتوى اللاندنج.

### H. Performance Patterns
- **Lazy loading** للصور بعد أول 8
- **Decoding async** لتفادي حجب الـ render
- **FOUC Loader** يخفي البنية لحد ما الـ render يكتمل
- **Cache-busting** على endpoints المقالات
- **No grid rebuild on URL bar toggle** (debounce by width only)

---

## 6. الميزات الأساسية

### 👁️ للزائر (Public)
- [x] Landing تسويقي مع 14 قسم قابل للتخصيص
- [x] بورتفوليوهات العملاء (`/<username>` أو دومين مخصص)
- [x] مدونة مقالات (`/articles`, `/<username>/articles`)
- [x] دعم AR/EN مع RTL تلقائي
- [x] WhatsApp Float + شريط سفلي للموبايل (3 أزرار قابلة للتخصيص)
- [x] Lightbox للصور والريلز (Instagram-style)
- [x] Before/After sliders
- [x] نموذج تواصل + Resend email
- [x] Drawer جانبي للموبايل

### 🎨 للعميل (Client Admin)
- [x] **إدارة المشاريع** (CRUD + categories + drag-reorder)
- [x] **رفع صور وفيديوهات** (إلى `/uploads`)
- [x] **محرر مشاريع متقدم** بـ modules:
  - Text (h1, h2, p)
  - Image
  - Photo Grid
  - Video (embed)
  - Before/After slider
  - Separator
- [x] **تخصيص الثيم** والألوان (8 paletteات جاهزة)
- [x] **ترتيب الأقسام** (drag & drop)
- [x] **تخصيص الشريط العلوي** (navbar_links)
- [x] **تخصيص الشريط السفلي للموبايل** (3 أزرار قابلة للضبط)
- [x] **محرر مقالات** WYSIWYG + HTML mode + رفع صور
- [x] **إحصائيات الزيارات** (Analytics)
- [x] **إدارة الشهادات والإنجازات والعملاء والشركاء**
- [x] **تغيير اسم المستخدم وكلمة المرور**

### 👑 للمالك (Owner Panel)
- [x] إدارة كل العملاء (إنشاء، تعديل، حذف)
- [x] تحديد مساحة التخزين لكل عميل
- [x] ربط دومينات مخصصة
- [x] تحرير اللاندنج بالكامل (14 قسم)
- [x] نظام موافقة لشهادات اللاندنج
- [x] مقالات اللاندنج

---

## 7. نموذج البيانات (Data Model)

| الجدول | الغرض | الأعمدة الأساسية |
|--------|------|------------------|
| `users` | حسابات العملاء | id, username, password, storage_limit_mb, custom_domain |
| `settings` | إعدادات JSON لكل عميل | user_id, key, value |
| `projects` | المشاريع | id, user_id, title, cover, images, modules, category |
| `articles` | المقالات | id, user_id, slug, title, content, mode, cover_url, tags |
| `logos` | شعارات العملاء/الشركاء | id, user_id, name, logo_url |
| `testimonials` | آراء العملاء | id, user_id, name, content, photo_url |
| `achievements` | الإنجازات (counters) | id, user_id, label, value, icon |
| `analytics_events` | تتبع الزيارات والمشاهدات | id, user_id, event_type, ip, country, timestamp |
| `messages` | رسائل نموذج التواصل | id, user_id, name, email, subject, message |

> **ملاحظة:** `user_id = 0` محجوز لمحتوى اللاندنج (مالك المنصة).

---

## 8. SEO الآلي

| الميزة | التطبيق |
|--------|--------|
| **Server-side meta injection** | title, description, OG, Twitter Card |
| **JSON-LD Schemas** | Person, Organization, BlogPosting, FAQPage, SoftwareApplication |
| **Hreflang** | للغتين (ar / en) |
| **OG Image generation** | ديناميكي عبر Pillow (`/og-image/<slug>.png`) |
| **sitemap.xml** | يُولَّد تلقائياً |
| **robots.txt** | موجود |
| **llms.txt** | لمحركات الذكاء الاصطناعي |

---

## 9. النشر (Deployment Pipeline)

```
GitHub Push
    ↓
Render Build (pip install -r requirements.txt)
    ↓
Gunicorn Start (server:app, 2 workers)
    ↓
Persistent Disk /var/data Mount
    ↓
Cloudflare DNS → Render
```

### بنية القرص الدائم
```
/var/data/
├── portfolio.db          # قاعدة البيانات SQLite
├── uploads/              # كل الملفات المرفوعة
│   └── <user_id>/        # مجلد لكل عميل
└── backups/              # نسخ احتياطية يومية
    └── portfolio_<date>.db
```

- **Auto-backups:** نسخة احتياطية يومية للـ DB
- **Storage tracking:** كل عميل بحدّ مساحة محدد، يُحسب من حجم رفعاته

---

## 10. الأمان (Security)

| البند | الحالة |
|------|--------|
| Session cookies (`HttpOnly`, `Secure` in prod) | ✅ |
| Owner panel محمي بـ secret + login | ✅ |
| Reserved paths لمنع تعارض الأسماء | ✅ |
| Rate limiting على نموذج الشهادات | ✅ |
| Cache-busting على endpoints المقالات | ✅ |
| `_can_edit_articles_for` للتحقق من الملكية | ✅ |
| ⚠️ `ADMIN_PASS=admin123` افتراضي | **يجب تغييرها فوراً** |
| ⚠️ لا يوجد CSRF tokens | للنظر مستقبلاً |
| ⚠️ SQLite + concurrent writes | محتمل `database is locked` تحت ضغط عالٍ |

---

## 11. الحدود الحالية والتوصيات المستقبلية

| البند | الحالي | التوصية المستقبلية |
|------|--------|---------|
| قاعدة البيانات | SQLite | الانتقال لـ **Postgres** عند نمو الحركة |
| الـ Workers | 2 | زيادة عند زيادة الحركة |
| CDN للصور | Render مباشرة | **Cloudflare R2 / S3** + CDN |
| Cache layer | لا يوجد | **Redis** للجلسات والإحصائيات |
| Search | لا يوجد | إضافة بحث في المقالات والمشاريع |
| Multi-language | AR/EN | توسيع لباقي اللغات (ES, FR, ...) |
| اختبارات آلية | لا يوجد | إضافة **pytest + Playwright** |
| Email notifications | فقط نموذج التواصل | إضافة إشعارات بريدية للأنشطة |
| Payment integration | لا يوجد | Stripe/Paymob لاشتراكات العملاء |

---

## 12. مؤشرات الأداء (KPIs)

| المؤشر | الهدف | الحالة |
|--------|------|-------|
| **Time to First Contentful Paint** | < 1.5s | ✅ |
| **Largest Contentful Paint** | < 2.5s | ✅ |
| **Mobile scroll** | 60fps | ✅ (تم إصلاح فلكر `resize` rebuild) |
| **SEO Score (Lighthouse)** | > 95 | ✅ |
| **Accessibility** | > 90 | ✅ |
| **Mobile-friendly** | 100% | ✅ |

---

## 📝 ملاحظات تطويرية

### نقاط القوة الحالية
- ✅ بنية بسيطة وسهلة الصيانة (لا build step)
- ✅ SEO آلي بالكامل
- ✅ Multi-tenant بكفاءة عالية
- ✅ تخصيص واسع بدون كود
- ✅ Mobile-first defensive CSS

### نقاط للتحسين
- 🔧 إضافة CSRF tokens
- 🔧 ترحيل لـ Postgres مع نمو المنصة
- 🔧 اختبارات آلية شاملة
- 🔧 CI/CD pipeline
- 🔧 Monitoring & error tracking (Sentry)

---

> **نهاية الوثيقة**
> هذا الـ PRD يعكس الحالة الفعلية للمشروع كما هو منشور حالياً على Render.
