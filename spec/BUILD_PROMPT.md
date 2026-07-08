# Build Prompt — paste this into the new project (with the `spec/` folder present)

---

You are building a **fresh rewrite** of an existing, working product called **ViralPX** — a
**multi-tenant portfolio-builder SaaS**. I am rebuilding it on a modern stack. Do **not** guess or
invent features: the `spec/` folder in this repo describes the current product **precisely**
(extracted from the real running code). **Read all of `spec/00`→`spec/05` before writing any code.**

## Exact target stack (must match — this mirrors my reference project "Novara")
- **Next.js (App Router, latest 16.x)** + **React 19** + **TypeScript**
- **Payload CMS 3** (`payload`, `@payloadcms/next`) — the admin + backend run inside the Next.js app
- **PostgreSQL** via `@payloadcms/db-postgres`
- **Cloudflare R2** for media via `@payloadcms/storage-s3` (S3-compatible; endpoint + bucket + keys from env)
- `@payloadcms/richtext-lexical` for rich text
- **Payload multi-tenant plugin** for tenant isolation
- Payload **localization**: locales `ar` + `en` (default per user's language)
- Package manager: pnpm

## Non-negotiable product requirements (all documented in `spec/`)
1. **Multi-tenant**: every client has their own portfolio at `/<username>` and optionally a **custom domain**
   (resolve host → tenant in Next middleware). All data scoped per tenant. See `spec/00` routing + `spec/05`.
2. **Bilingual (AR/EN) everywhere**, with **RTL** for Arabic. Most content fields are AR+EN pairs — use Payload localization.
3. **The client dashboard** (`spec/02`) is the highest-priority surface — reproduce its capabilities faithfully
   (projects, highlights, design/theme, sections order, navbar, mobile bar, content, logos, achievements,
   testimonials, articles, social). It can look cleaner than the original, but must not lose control/fields.
4. **Projects display + the module page-builder** (`spec/03`) is the second priority. The project `modules[]`
   map to a **Payload Blocks field** (block types: text, image, grid (array of images), video, beforeafter, separator).
   Reproduce the grid/reel/story players as client components with the exact interaction/perf rules in `spec/03`.
5. **Media pipeline**: on upload, store on R2; generate a small thumbnail (Payload `imageSizes`, e.g. a `thumb` ~640px,
   prefer WebP) — grids/bubbles use the thumbnail, detail/story use full res. Enforce a per-tenant storage quota.
6. **SEO**: SSR meta (title/description/OG/Twitter), hreflang ar/en, canonical, JSON-LD (Person, Organization,
   BlogPosting, FAQPage), dynamic OG images (use `@vercel/og`/Satori), robots.txt, sitemap.xml, llms.txt. See `spec/05`.
7. **Performance**: lazy images, thumbnails on grids, no re-render/reflow on scroll (see the iOS notes in `spec/03`),
   avoid `backdrop-filter`+`overflow` over images.

## Data-model mapping (from `spec/01`)
- Collections: `users`(auth, is_owner) / `tenants` (or use the multi-tenant plugin's tenant), `projects`,
  `articles`, `media` (upload→R2), `logos`, `testimonials`, `achievements`, `visits` (analytics).
- The per-tenant **settings** key/value store → a **`site-settings`** global scoped per tenant (or a JSON/group on the tenant):
  social links, colors, design system (`style_*`), `theme_config`, sections[], navbar_links[], mobile_bar,
  highlights[], categories, content{}, hero-cover controls, grid column counts. Full key list in `spec/01`.
- `projects.modules` → **Blocks**; `projects.images` → array/upload relationship; `project_type`
  (grid|free|stacked) → a select the frontend uses to pick the detail-page layout.
- The **landing page** (owner marketing site, `spec/05`) is owner-managed content (a separate global / tenant 0).

## Design system (from `spec/05`)
Apply as CSS variables per tenant: colors (accent/bg/bg2/text/subtext) or a bg preset (dark/ocean/sunset/forest/mono/pearl);
font pairs (AR+EN Google fonts — default Cairo/Montserrat, modern Tajawal/Inter, editorial Almarai/Playfair Display,
elegant Markazi Text/Cormorant Garamond, bold Cairo/Bebas Neue); component variants (card solid|glass|outline,
navbar blur|solid|transparent, button rounded|sharp|pill); animations fade-up|fade|none (scroll-reveal). Layout
variants per section as listed in `spec/02` §5 and `spec/03`.

## How to work (IMPORTANT — phased, local first)
Build **locally** (dev) and go in phases. **Do not attempt everything at once.** After each phase, stop and
show me the result before continuing.

- **Phase 0 — Scaffold**: create the Next.js + Payload app, connect a local Postgres, wire R2 storage-s3 (env),
  set up localization (ar/en) + the multi-tenant plugin + auth. Get `payload` admin running at `/admin`. Confirm it boots.
- **Phase 1 — Data model**: implement ALL collections + the `site-settings` global with every field from `spec/01`,
  including the `projects` Blocks (modules). Generate types. **Show me the collections/config before building UI.**
- **Phase 2 — Public portfolio**: the `/<username>` page rendering sections + the projects display + module blocks
  + highlights/story + lightboxes (client components), SSR + SEO. Match `spec/03` + `spec/05`.
- **Phase 3 — Client dashboard**: reproduce the editing capabilities of `spec/02`. Use Payload admin where it fits;
  build custom admin components / a custom client UI for the visual pickers (theme/colors/shapes) and live preview.
- **Phase 4 — Landing + articles + analytics + custom-domain middleware + owner tools.**
- **Phase 5 — Data migration** from the old system (I'll provide a SQLite export; map to Postgres/Payload).

## Environment (I will provide real values)
`DATABASE_URI` (Postgres), `PAYLOAD_SECRET`, R2: `R2_ENDPOINT/R2_BUCKET/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_PUBLIC_URL`,
`RESEND_API_KEY/RESEND_FROM`. Use a local Postgres + a dev R2 bucket for local development.

## Start now with Phase 0 only
Scaffold the project, get Payload + Postgres + R2 + localization + multi-tenant + auth running locally, and confirm
the admin boots. Then stop and tell me what you set up and what env values you need from me. Ask before moving to Phase 1.
