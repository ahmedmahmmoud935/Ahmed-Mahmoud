# ViralPX — Data Model (exact)

> Extracted verbatim from `server.py`. In Payload these become collections; the
> `settings` key/value store becomes a per-tenant **`site-settings`** global (or a
> JSON/group field on the tenant).

## Relational tables (SQLite → Postgres collections)

### users
`id, username (unique), password, storage_limit_mb (default 500), storage_used_mb (real), is_owner (0/1), created_at`
> Note: passwords are currently plaintext — in Payload use its built-in hashed auth.

### projects
```
id, user_id, title, category, description,
media_type   ('image' | 'video'),
cover_url, video_url,
sort_order,
project_type ('grid' | 'free' | 'stacked'),  ← controls the detail-page render
modules      (JSON array — the page builder, see 03),
aspect_ratio ('9:16' default),
video_kind   ('reel' | 'video'),
created_at
```

### project_images
`id, project_id (FK cascade), url, sort_order`
> The gallery images for a project (separate from `modules`).

### domains
`user_id (unique), domain (unique), created_at` — custom-domain → tenant mapping.

### visits (analytics)
`id, user_id, visited_at, visitor_id, page, project_id, country, device, referrer`

### client_logos
`id, user_id, name, logo_url, website_url, sort_order, created_at`

### testimonials
`id, user_id, name, role, company, content, avatar_url, rating (1-5, default 5),
source ('admin' | 'public'), approved (0/1, default 1), sort_order, created_at`

### achievements
`id, user_id, icon_url, title (ar), title_en, value (string e.g. "50+"), sort_order`

### articles
```
id, user_id, slug, title_ar, title_en, excerpt_ar, excerpt_en,
cover_url, content, mode ('markdown' | 'html'), tags (comma string),
published (0/1), read_min, created_at, updated_at
```
Unique index: `(user_id, slug)`.

### settings — per-tenant key/value (JSON values)
`(user_id, key) PK, value (TEXT — JSON or scalar)`. **This is the heart of the config.** All keys below.

---

## Settings keys (defaults from `default_settings`)

### Social
- `whatsapp, behance, instagram, linkedin, facebook, vimeo` — string URLs/handles
- `social_visible` — array, default `["whatsapp","behance","instagram","linkedin","vimeo"]`

### Media / brand
- `photo_url` (about photo), `hero_cover_url`, `brand_logo_url`, `favicon_url`
- `brand_logo_scale, brand_logo_offset_x, brand_logo_offset_y` (logo positioning)
- `avatar_url`

### Hero cover controls
- `hero_cover_size` ('cover'|'contain'|'NN%'), `hero_cover_pos_x` (0-100), `hero_cover_pos_y` (0-100),
  `hero_cover_overlay` (0-100 dark overlay %), `hero_height` (vh, default 85)

### Grid column counts (responsive)
- `image_cols_mobile/tablet/desktop` (default 2/3/4)
- `video_cols_mobile/tablet/desktop` (default 2/3/4)
- `freegrid_cols_mobile/desktop` (default 1/2)

### Categories
- `image_categories` — array (default: Social Media, Brand Identity, Logo Design, Print Design, Packaging, Posters, UI/UX)
- `video_categories` — array (default: Reels, Motion Graphics, Video Editing, AI Videos, Promo Ads, Tutorials)

### Project section tabs
- `proj_tabs` — object `{ designs, reels, videos }`, each `{ visible, label_ar, label_en, icon }`

### Navigation & layout
- `navbar_links` — array of `{ id, label_ar, label_en, visible }` (default: about, expertise, experience, projects, contact)
- `sections` — array of `{ id, label_ar, label_en, visible, order }` (see full list below)
- `mobile_bar` — `{ enabled, buttons: [ {pos:'left|center|right', type:'section|whatsapp|articles|link', target, icon, label_ar, label_en} ×3 ] }`
- `highlights` — array of `{ title_ar, title_en, cover_url, items: [ {type:'image|video', url} ] }`

### Colors
- `colors` — `{ accent, bg, bg2, text, subtext }` (default #F97316 / #0A0A0A / #111111 / #FFFFFF / #999999)
- `style_bg_preset` (dark|ocean|sunset|forest|mono|pearl), `style_bg_type` (solid|gradient),
  `style_bg_color1, style_bg_color2`

### Design system (the "Design" tab)
- `style_theme` (default | kinetic)  ← **note: kinetic being retired/cleaned; treat 'default' as the norm**
- `style_hero` (centered | split | massive | cover-full | minimal)
- `style_about` (classic | visual | simple)
- `style_projects` (grid | masonry | list | freegrid)
- `style_contact` (classic | split)
- `style_skills` (tags | inline | bars)
- `style_tools` (classic | compact)
- `style_exp` (classic | timeline)
- `style_font` (default | modern | editorial | elegant | bold)
- `style_direction` (auto | rtl | ltr)
- `style_cursor` (default | dot-ring)
- `style_anim` (fade-up | fade | none)
- `theme_config` — `{ components: { card:'solid|glass|outline', navbar:'blur|solid|transparent', button:'rounded|sharp|pill' }, tokens?:{...} }`
- Per-theme override snapshots: `theme_overrides` (object keyed by theme id), and `_custom_<key>` flags (mark a field as user-customized so a theme preset won't override it)

### Footer
- `footer_logo_size, footer_logo_align, footer_socials_align, footer_copy_align`

### Content blocks
- `content` — object with sub-objects (see below)

### Internal (added by API, not stored)
- `_username, _user_id`

---

## `content` object shape (the text of each section)
```json
{
  "hero":   { "name_en","name_ar","title_en","title_ar","btn1_en","btn1_ar","btn2_en","btn2_ar" },
  "about":  { "text_en","text_ar","tags_en","tags_ar" },   // tags = comma-separated
  "education":  { "items": "[]" },   // JSON string: array of education entries
  "skills":     { "items_en","items_ar" },  // comma-separated soft skills
  "tools":      { "items": "[]" },   // JSON string: array of tools {name, icon/img}
  "experience": { "items": "[]" },   // JSON string: array of jobs
  "expertise":  { "title_en","title_ar","items": "[]" },  // services list
  "projects":   { "title_en","title_ar","subtitle_en","subtitle_ar" },
  "contact":    { "title_en","title_ar","subtitle_en","subtitle_ar","email","phone" }
}
```

## Full section list (portfolio `sections`, order 0-11)
`hero, about, projects, achievements, expertise, testimonials, logos, experience, tools, education, skills, contact`
Each: `{ id, label_ar, label_en, visible, order }`. Order + visibility are user-editable (drag-reorder).

## Landing page config (`DEFAULT_LANDING`, owner-only, stored under user_id=0)
- `brand` `{ name, logo_url, tagline_ar, tagline_en }`
- `sections` (11): hero, features, projects, examples, stats, how, pricing, testimonials, faq, contact, cta
- `style` `{ design (modern|minimal|bold|soft|editorial), theme, primary_color, primary_color_dark, bg_color, bg_color_alt, text_color, text_muted, font_ar, font_en, border_radius }`
- plus per-section content objects (hero, features, pricing, faq, etc.) — see landing.html for exact fields
- `mobile_bar` (same shape as portfolio)
