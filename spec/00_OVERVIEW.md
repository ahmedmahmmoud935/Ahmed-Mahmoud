# ViralPX — Product Spec (Overview)

> Accurate description extracted from the actual current codebase (Flask + SQLite +
> vanilla JS). Intended as the rebuild brief for a Next.js + Payload CMS + Postgres + R2
> version. **Nothing here is speculative** — every feature/field is taken from the running code.

## What the product is
A **multi-tenant portfolio-builder SaaS**. Each client gets their own portfolio site,
editable from a dashboard with no code. There is also a marketing **landing page** at the
root domain, and a blog/**articles** system. An **owner** manages all clients.

## Roles
| Role | Access | Auth |
|------|--------|------|
| **Visitor** | public portfolios, landing, articles | none |
| **Client** | own dashboard (`/admin`) | username + password (session cookie) |
| **Owner** | owner panel (`/owner`) + landing editor | separate secret + login |

## URL structure (routing to replicate)
- `/` → landing page (SaaS marketing). If a custom domain maps to a client → that client's portfolio.
- `/<username>` → a client's portfolio (pretty URL). `username` must not be a reserved path.
- `/u/<username>` → legacy portfolio URL.
- `/<username>/articles` and `/<username>/articles/<slug>` → client's blog.
- `/articles` and `/articles/<slug>` → landing (owner) blog.
- `/admin` → client dashboard. `/owner` → owner panel.
- Custom domains: a client can map their own domain → resolves to their portfolio (via `domains` table).
- **Reserved paths** (cannot be usernames): admin, owner, api, uploads, u, articles, og-image, editor, testimonial, landing, static, assets, public, robots.txt, sitemap.xml, llms.txt, favicon.ico, and the `.html` variants.

## Current tech (being replaced)
- Backend: Flask + Gunicorn, SQLite at `/var/data/portfolio.db`
- Frontend: 5 standalone HTML files with inline CSS/JS (index, admin, owner, articles, landing) + editor.html
- Storage: Cloudflare R2 (media) + local disk fallback; images auto-converted to WebP + a `_t.webp` thumbnail
- CDN: Cloudflare in front of everything
- Email: Resend API (contact form + testimonial notifications)
- Auto DB backups (WAL-consistent) local + off-site to a private R2 bucket

## Target tech (rebuild)
- Next.js + Payload CMS 3 + PostgreSQL + R2 (`@payloadcms/storage-s3`)
- Keep: multi-tenant, custom domains, WebP+thumbnail pipeline, SSR/SEO, AR/EN

## Bilingual
Everything is **Arabic + English**. Most text fields exist as `_ar` and `_en` pairs.
Direction: auto (RTL for Arabic, LTR for English) — overridable per site (`style_direction`).

## The 6 spec files
1. `00_OVERVIEW.md` — this file
2. `01_DATA_MODEL.md` — DB tables, settings keys, all JSON shapes
3. `02_DASHBOARD.md` — every dashboard tab + control (the client editor) — **most detail**
4. `03_PROJECTS_DISPLAY.md` — project layouts, cards, module page-builder, detail page, lightboxes — **most detail**
5. `04_API.md` — every endpoint
6. `05_PUBLIC_SITE.md` — public portfolio sections, landing, articles, highlights, SEO, multi-tenant
