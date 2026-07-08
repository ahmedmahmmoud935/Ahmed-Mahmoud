# ViralPX — Public Site (portfolio, landing, articles, SEO)

## Portfolio page (`/<username>`)
Renders the tenant's sections in the order/visibility from `settings.sections`, styled by the
design system. Full section list & their content come from `settings.content` (see 01/02).

### Sections (each has a layout variant — see Design tab)
- **hero** — name + role + 2 CTA buttons; optional cover image (size/pos/overlay/height). Layouts: centered/split/massive/cover-full/minimal.
- **about** — photo + bio text + tags. Layouts: classic/visual/simple.
- **projects** — the projects system (see `03_PROJECTS_DISPLAY.md`). Highlights circles render above it.
- **achievements** — animated counters (title + value).
- **expertise/services** — service cards.
- **testimonials** — client reviews (approved only). Public can submit.
- **logos** — client logos strip.
- **experience** — job timeline. Layouts: classic/timeline.
- **tools** — tool/software grid. Layouts: classic/compact.
- **education** — education entries.
- **skills** — soft-skill chips. Layouts: tags/inline/bars.
- **contact** — form (name/email/subject/message) → Resend email; + email/phone. Layouts: classic/split.
- **footer** — brand logo + owner name + social icons + copyright (alignments configurable).

### Chrome
- **Navbar** — logo + links (`navbar_links`) + language toggle + Articles link. Variant blur/solid/transparent.
- **Mobile**: hamburger → side drawer; **bottom bar** (3 configurable buttons); WhatsApp float (desktop).
- **Highlights** story circles above projects; **story viewer** 9:16.

## Design system tokens (apply as CSS variables)
- Colors: `--accent, --bg, --bg2, --text, --sub` from `settings.colors` (or a bg preset).
- **BG presets**: dark `#0a0a0a/#111`, ocean `#0a1628/#0f1f3d` (gradient), sunset `#1a0a14/#3a1520`, forest `#0a1a0f/#0f2a1f`, mono `#1a1a1a/#0a0a0a`, pearl `#fafaf5/#fff` (light). Each defines bg/bg2/text/sub + solid|gradient + light flag.
- **Font pairs** (Google Fonts, AR + EN): default Cairo/Montserrat · modern Tajawal/Inter · editorial Almarai/Playfair Display · elegant Markazi Text/Cormorant Garamond · bold Cairo/Bebas Neue. Arabic elements use the AR font; Latin/display elements use the EN font.
- Component variants: card solid|glass|outline, navbar blur|solid|transparent, button rounded|sharp|pill.
- Animations: `fade-up | fade | none` — scroll-reveal via IntersectionObserver.
- Direction: auto (RTL for Arabic).

## Themes
A structured **theme registry** (`themes/registry.json`, served at `/api/theme-registry`): each theme has
`{ id, name{en,ar}, tokens, components, layout, anim, legacy_map }`. `legacy_map` translates a theme to the
`style_*` settings the renderer understands, so a JSON-only theme renders with no code changes.
Current themes: default (custom) + kinetic (animated — being cleaned/retired). In the rebuild, model themes
as data and apply tokens/variants as above.

## Landing page (`/`)
Owner-managed marketing site (config under user_id=0, `DEFAULT_LANDING`). Sections: hero, features, projects
showcase, live examples, stats, how-it-works, pricing, testimonials (public submit + moderation), faq, contact, cta.
Own style block (design preset modern/minimal/bold/soft/editorial + colors + fonts + radius) and its own mobile bar.

## Articles / blog
- Per tenant (`/<username>/articles`) and for landing (`/articles`).
- List page (cards: cover thumbnail, title, date, read time, tags) + single article page (cover, title, meta, HTML content).
- Content stored as HTML (`mode='html'`; legacy markdown rendered). Rich editor + raw HTML in the dashboard.
- Navbar matches the parent site; each article has SEO meta + JSON-LD BlogPosting.

## SEO (automatic — replicate)
- **SSR meta injection**: title, description, Open Graph, Twitter Card, hreflang (ar/en), canonical.
- **JSON-LD**: Person, Organization, SoftwareApplication, BlogPosting, FAQPage.
- **Dynamic OG images**: `/og-image/<slug>.png` (currently Pillow-generated) — in Next use `@vercel/og`/Satori.
- `robots.txt`, `sitemap.xml`, `llms.txt`.
- Fast: images WebP + thumbnails + lazy; CDN; no layout-thrash on scroll.

## Multi-tenant & domains (must replicate)
- `/<username>` → that tenant's data (username not in reserved list).
- Custom domain → tenant via the `domains` table; the request host is resolved to a user_id and their portfolio is served.
- Everything scoped by `user_id`. In Next.js: middleware resolves host/username → tenant; Payload access control enforces isolation.
- Per-tenant storage quota (bytes counted on upload/delete).

## Media pipeline (keep)
- Upload → convert to WebP (max 1920px) + generate `<name>_t.webp` thumbnail (≤640px) → store on R2 → serve via `cdn.viralpx.com`.
- Videos: uploaded to R2 or external embeds (YouTube/Vimeo) for reels.
- Grids/bubbles use the thumbnail; detail/story use full res.

## Email (Resend)
Contact form submissions + new-testimonial notifications. Env: `RESEND_API_KEY`, `RESEND_FROM`.
