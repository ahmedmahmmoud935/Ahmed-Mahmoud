# ViralPX — API surface (exact routes)

> All current endpoints. In the Next.js+Payload rebuild these map to Payload REST/GraphQL
> + a few custom Next route handlers (upload processing, import tools, analytics, contact).

## Auth
- `POST /api/auth/login` — client login (username, password) → session cookie
- `POST /api/auth/logout`
- `GET  /api/auth/check` — is a client logged in
- `PUT  /api/auth/credentials` — change own username/password (needs old password)
- `POST /api/owner/login` · `POST /api/owner/logout` · `GET /api/owner/check` — owner session

## Owner (manage tenants)
- `GET  /api/owner/users` — list clients
- `POST /api/owner/users` — create client (username, password)
- `DELETE /api/owner/users/<id>`
- `PUT  /api/owner/users/<id>/password`
- `PUT  /api/owner/users/<id>/storage` — set storage_limit_mb
- `GET/PUT /api/owner/users/<id>/domain` — custom domain
- `GET  /api/owner/stats` — platform overview

## Settings (per-tenant config)
- `GET  /api/settings[?user_id=|?username=]` — returns the whole settings object (+ `_username`, `_user_id`). Public read for portfolio rendering.
- `PUT  /api/settings` — save any subset of keys (validated/normalized; unknown keys pass through). Handles image uploads embedded as data URLs (photo/hero_cover/brand_logo/favicon/tool images).

## Projects
- `GET  /api/projects[?user_id=]` — list (public)
- `POST /api/projects` · `PUT /api/projects/<id>` · `DELETE /api/projects/<id>`
- `PUT  /api/projects/reorder` — save sort order
- `GET/PUT /api/projects/<id>/modules` — the page-builder blocks

## Media / import
- `POST /api/upload` — multipart; `kind=image|video`; returns `{url}`; images → WebP + `_t.webp` thumbnail; quota enforced
- `POST /api/proxy-image` · `POST /api/proxy-images` — fetch remote image(s) server-side (bypass hotlink/CORS)
- `POST /api/import/save-images` — save imported images to a project
- `POST /api/vimeo/fetch` — pull Vimeo data (needs `vimeo_token`)
- `POST /api/video/thumbnail` — extract a video thumbnail
- `GET  /bookmarklet.js` · `POST /api/bookmarklet/submit` · `GET /api/bookmarklet/get/<id>` — Behance import bookmarklet flow

## Content collections (all per-tenant, public GET)
- Logos: `GET/POST /api/logos`, `PUT/DELETE /api/logos/<id>`, `PUT /api/logos/reorder`
- Testimonials: `GET/POST /api/testimonials`, `POST /api/testimonials/submit` (public), `PUT/DELETE /api/testimonials/<id>`, `PUT /api/testimonials/reorder`; page `/testimonial/<username>`
- Achievements: `GET/POST /api/achievements`, `PUT/DELETE /api/achievements/<id>`, `GET /api/achievements/public`
- Articles: `GET /api/articles[?username=]`, `GET /api/articles/<id>`, `POST /api/articles`, `PUT/DELETE /api/articles/<id>`

## Landing (owner-only content at root, user_id=0)
- `GET  /api/landing` — public read (marketing page data)
- `PUT  /api/landing` — owner save (deep-merged)
- `POST /api/landing/reset`
- Landing testimonials: `POST /api/landing/testimonials/submit` (public, rate-limited), `/approve`, `/reject` (owner)

## Analytics
- `POST /api/track` — record a visit `{page, project_id, ...}` (country/device derived server-side)
- `GET  /api/analytics?days=N` — aggregated: total_visits, unique_visitors, devices, top_projects, referrers

## Misc / infra
- `GET  /api/me/storage` — client's storage usage
- `POST /api/contact` — contact form → Resend email
- `GET  /api/resolve-user?username=` — username → user_id
- `GET  /api/users/by-username/<username>`
- `GET  /api/theme-registry` · `GET /api/theme-registry/<id>/legacy` — theme registry (external JSON)
- `GET  /api/backup-now?key=` · `GET /api/db-backup?key=` — trigger/download DB backup (owner secret)
- `GET  /uploads/<path>` — serve local media (legacy; new media is on R2/CDN)
- SEO: `/llms.txt`, `robots.txt`, `sitemap.xml`, `/og-image/<slug>.png` (dynamic OG image via Pillow)

## Page routes (SSR HTML with meta injection)
- `/` landing · `/<username>` & `/u/<username>` portfolio · `/<username>/articles[/<slug>]` · `/articles[/<slug>]`
- `/admin` · `/owner` · `/admin/editor/<pid>` (project module editor)
