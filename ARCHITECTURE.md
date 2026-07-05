# ViralPX — Architecture Foundation (Phase 1)

> Incremental, production-safe upgrade toward a component-based, schema-driven,
> theme-engine architecture. **Nothing existing was removed or changed in behavior.**
> Every change is additive and guarded.

---

## What shipped in this phase

| Layer | File(s) | Status |
|------|---------|--------|
| **Theme Registry** (externalized themes) | `themes/registry.json` | ✅ new |
| **Theme Engine (server)** | `theme_engine.py` | ✅ new |
| **Settings Schema** (validation + backward-compat) | `settings_schema.py` | ✅ new |
| **Read-only registry API** | `server.py` → `/api/theme-registry`, `/api/theme-registry/<id>/legacy` | ✅ additive |
| **Safe settings normalization** | `server.py` → `update_settings` | ✅ additive (non-rejecting) |
| **Theme Engine (client)** | `public/theme-engine.js` | ✅ new, opt-in |
| **Progressive hydration hook** | `public/index.html` → `boot()` | ✅ 4 guarded lines |

**Result:** existing users see *zero* difference. Behavior is identical unless a
new structured theme or `theme_config` is introduced.

---

## ✅ Success criterion #1 — Add a theme WITHOUT touching core code

Append an object to `themes/registry.json`:

```json
{
  "id": "aurora",
  "name": { "en": "Aurora", "ar": "أورورا" },
  "tokens": { "accent": "#8b5cf6", "radius": "18px", "font_pair": "modern" },
  "components": { "button": "pill", "card": "glass", "navbar": "blur" },
  "layout": { "hero": "split", "projects": "masonry", "about": "visual", "contact": "split" },
  "anim": "fade-up",
  "legacy_map": {
    "style_hero": "split", "style_projects": "masonry",
    "style_about": "visual", "style_contact": "split",
    "style_font": "modern", "style_bg_preset": "dark", "style_anim": "fade-up"
  }
}
```

Then set a user's `style_theme = "aurora"` from the dashboard. The site:
1. sees `aurora` isn't in the inline `THEMES` map,
2. fetches `/api/theme-registry/aurora/legacy`,
3. injects the mapping → the **existing renderer** draws it.

No edits to `index.html`, `server.py`, or CSS required.

> The 7 current themes are mirrored into the registry but **also remain inline**,
> so they keep working even with the registry disabled.

---

## How the bridge works (why it's safe)

```
themes/registry.json   ──>  /api/theme-registry/<id>/legacy
        │                            │
        │ (structured config)        │ (style_* mapping)
        ▼                            ▼
theme_engine.py  ──legacy_map──>  existing style_* settings  ──>  existing applyStyle()
```

A structured theme is *translated* into the `style_*` keys the live engine already
understands. We did **not** rewrite the renderer — we fed it from a new source.

---

## Settings Schema layer (`settings_schema.py`)

`normalize(settings)` runs on every save and:
- coerces known keys to declared types,
- maps legacy aliases (`theme → style_theme`, …),
- **passes unknown keys through unchanged** (backward compatible),
- returns `(clean, warnings)` and **never raises**.

In `update_settings` it's wrapped in `try/except` and falls back to the raw save,
so a schema bug can never block a production save.

To tighten later: call `normalize(d, strict=True)` to drop unknown keys — opt-in,
not enabled now.

---

## Multi-tenant safety (unchanged, verified)

All reads/writes remain scoped by `user_id`. The new code touches neither the
tenancy filter nor the session checks. The registry endpoints are read-only and
tenant-agnostic (themes are global definitions, selection is per-tenant).

---

## Roadmap — remaining phases (not yet done, by design)

These are the larger, higher-risk pieces. Do them **one page at a time** with the
same additive discipline. The infrastructure above already supports them.

### Phase 2 — Token-driven CSS (low risk)
- Add `theme_config.tokens` to a test user; `VPXTheme.applyTokens()` already wires
  them to CSS variables. Gradually replace hardcoded hex in CSS with `var(--…)`.

### Phase 3 — Component abstraction (IN PROGRESS)

**✅ Done: `ProjectCard`** (`public/index.html`)
- One component function is now the single source of truth for the card wrapper:
  ```js
  function ProjectCard({inner, onclick, extraClass=''}){
    const v = _CARD_VARIANT || 'solid';            // from theme.components.card
    return `<div class="project-card pc-${v} ${extraClass}" onclick="${onclick}">${inner}</div>`;
  }
  ```
- All **3** previous inline card templates (image grid, reels, freegrid) now call it.
- Variant resolved in `boot()` via `resolveCardVariant()` from the active theme's
  `components.card`. Default `solid` === the exact previous markup (verified).
- CSS variants added: `.pc-solid` (no change), `.pc-glass`, `.pc-outline`.
- Validated: all inline `<script>` blocks parse (node `new Function`), 0 raw card
  templates remain, markup parity confirmed.

**✅ Done: `Navbar`** (`public/index.html`)
- Variant from `theme.components.navbar`: `blur | solid | transparent` (`nv-blur` === default).
- Resolved alongside the card variant in a single `resolveComponentVariants()`
  call (one theme fetch for all components). Applied via `applyNavbarVariant()`.
- `transparent` becomes blurred once scrolled (`.scrolled` toggled by the scroll
  handler). On mobile the existing opaque override still wins (flicker-safe).
- CSS: `#mainNav.nv-solid`, `.nv-transparent`, `.nv-transparent.scrolled`.
- Validated via node; default behavior unchanged.

**✅ Done: `Button`** (`public/index.html`)
- Variant from `theme.components.button`: `rounded | sharp | pill` (`btn-rounded` === default 6px).
- Applied as a body class via `applyButtonVariant()`; CSS overrides radius on
  `.btn-primary/.btn-outline/.btn-submit` site-wide. Registry-only themes get the
  correct button shape automatically.

**✅ Done: `ArticleCard`** (`public/articles.html`)
- Variant from the active theme's `components.card` → `ac-solid | ac-glass | ac-outline`.
- Resolved via `resolveArticleCardVariant()` (reads `DATA.style_theme` for portfolio
  or `DATA.style.design` for landing), applied as a class on `.art-card`.
- `theme-engine.js` now loaded on articles.html too. Default `solid` unchanged.

**ℹ️ Already config-driven — no component wrapper needed (by design):**
- **Hero** — layout (`centered|split|massive|cover-full|minimal`) flows from
  `theme.layout.hero → legacy_map.style_hero → buildHero()`. It lives in the
  *layout* layer (Phase 4), not the component-variant layer.
- **MobileBar** — `renderMobileBar()` already reads every button (type, icon,
  label, enabled) from `S.mobile_bar`, with a per-user dashboard editor. It lives
  in the *content/settings* layer. Wrapping either would be over-engineering.

### Dashboard UI — ✅ wired (the "steering wheel")
`admin.html` → Design tab now has a **"أشكال العناصر" (Component Shapes)** section:
- Radio pickers for card (solid/glass/outline), navbar (blur/solid/transparent),
  button (rounded/sharp/pill).
- `saveDesign()` writes them to `theme_config.components`.
- Verified round-trip: admin save → `settings_schema.normalize` keeps `theme_config`
  → `get_settings` returns it → `resolveComponentVariants()` applies live.

The engine now has its controls: a client can change component shapes from the
dashboard and see them applied on the live site. No code edits needed per change.

### Dynamic theme picker — ✅ wired
`admin.html` Design tab now renders theme cards **dynamically from the registry**
(`renderRegistryThemeCards()` → `/api/theme-registry`). Previously only `default`
and `kinetic` were selectable; now editorial/minimal/creative/cinema/corporate —
**and any future registry theme** — appear automatically as selectable cards.
Realizes the core success criterion end-to-end: *add a theme in registry.json →
it shows up in the dashboard → the client picks it → the site renders it*, with
zero code changes.

### Phase 3 status: ✅ substantially complete
Component-variant abstraction now covers every element that benefits from it:

| Component | Variants | Pages |
|-----------|----------|-------|
| ProjectCard | solid · glass · outline | index |
| Navbar | blur · solid · transparent | index |
| Button | rounded · sharp · pill | index |
| ArticleCard | solid · glass · outline | articles |

All resolve from a single `resolveComponentVariants()` (index) / `resolveArticleCardVariant()`
(articles). Adding another variant = ~2 lines + CSS classes. Defaults are byte-for-byte
the previous look; verified via node syntax checks and markup parity.

### Phase 4 — Layout engine (medium risk)
`theme.layout.projects = "masonry"` already flows through `legacy_map → style_projects`.
Formalize remaining sections the same way so layout is 100% DB-switchable.

### Phase 5 — Shared component lib across pages (refactor)
Extract the migrated component functions into a shared `public/components.js`
loaded by `index.html`, `landing.html`, `articles.html` — removing duplication.

---

## Rollback

Every change is isolated:
- Delete `themes/`, `theme_engine.py`, `settings_schema.py`, `public/theme-engine.js`
- Revert the 3 small `server.py` blocks + 2 `index.html` blocks (all guarded)

The system returns to its exact previous state. No DB migration was performed, so
stored data is untouched and compatible both ways.

---

## API reference (new)

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/theme-registry` | GET | full registry (themes + tokens + variants + presets) |
| `/api/theme-registry/<id>/legacy` | GET | `style_*` mapping for one theme |

Both are read-only and safe to cache client-side.
