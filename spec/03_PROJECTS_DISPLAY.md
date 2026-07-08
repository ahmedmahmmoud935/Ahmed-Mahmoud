# ViralPX — Projects Display & Editor — full spec

> How projects render on the public portfolio + the editor that produces them.
> **Priority area.** Extracted from `index.html` (render) and `editor.html` (editor).

## A project (data)
```
title, category, description,
media_type: 'image' | 'video',
cover_url, video_url, video_kind: 'reel' | 'video', aspect_ratio (e.g. '9:16'),
project_type: 'grid' | 'free' | 'stacked',   ← how the detail page renders
images: [url, ...],                            ← gallery images (project_images table)
modules: [ block, ... ]                        ← the page-builder blocks (JSON on the project)
```

---

## 1. The projects SECTION on the portfolio
Header (title + subtitle from `content.projects`) → filter tabs → category filter → grid.

### Filter tabs (`proj_tabs`)
Three toggleable tabs, each with custom label (AR/EN) + FA icon:
- **Designs** → image projects → shown as an **image grid**
- **Reels** → vertical videos → **9:16 grid**, click opens a **story-style vertical player**
- **Videos** → **16:9 freegrid**, click opens the video player
If only one tab is visible, the filter bar is hidden. First visible tab is the default.

### Category filter
Pills built from `image_categories` / `video_categories` (per active tab) + "All". Filters the grid.

### Grid layouts (`style_projects` → a `mode-*` class)
- `mode-image` — Behance-style uniform grid. Desktop 3 cols (responsive via `image_cols_*`), `aspect-ratio:4/3`, gap.
- `mode-video` — reels: 4 cols, `aspect-ratio:9/16` (vertical); a card can be `.horizontal` (4/5).
- `mode-freegrid` — videos: 16:9 uniform, cols via `freegrid_cols_*`.
- `mode-masonry` — CSS columns (3 desktop / 2 / 1), variable heights.
- `mode-list` — vertical stacked list.

### Project CARD
`<div class="project-card pc-{variant}">` where variant = `theme_config.components.card` (solid|glass|outline).
- Cover: `<img>` (uses the `_t.webp` thumbnail with onerror fallback to full).
- Hover **overlay**: gradient + title + category (fades in on hover; disabled on mobile).
- Video cards add a **play button** + (reels) a film badge; the thumbnail is a `.vid-thumb`.
- **Card variants**: solid = plain; glass = border + shadow (cover stays full-bleed); outline = border. *(The cover must never be repositioned/hidden by the variant.)*
- Click:
  - image → **openProject(idx)** → project detail page
  - reel/video → **openVideoLightbox(idx)** → vertical/story player

### Performance rules (must preserve)
- Grid re-renders **only when width changes** (column count), never on height/scroll (iOS URL-bar toggle caused flicker before).
- Images: `loading=lazy` after the first ~8, `decoding=async`, thumbnails on grids, full res on detail.
- Avoid `backdrop-filter` + `overflow:hidden` on the same element containing an image (Safari hides it).

---

## 2. Project DETAIL page (`project_type`)
A full-screen overlay (`#projectPage`) with a sticky top nav (back button) + content + footer.
Three render modes:

### `grid` (default)
No top banner. Centered title/category/description. Then a **3-col image grid** of `images[]` (aspect 4/5),
click any → lightbox.

### `free` (Behance-style — the module page builder)
No banner. Renders `modules[]` in order (see modules below). Before/after sliders initialized.
Gallery built from image/grid modules for the lightbox.

### `stacked`
Top **cover** image (banner) + header + the rest of `images[]` stacked full-width.

Back navigation uses history (browser back closes the detail page). On mobile the back button floats at the bottom.

---

## 3. Modules — the page builder (`modules[]`)
Each project (esp. `project_type:'free'`) is built from ordered blocks. Block types + fields:

| type | fields | renders as |
|------|--------|-----------|
| `text` | `textType` (h1/h2/p — also legacy heading/subtitle/paragraph), `value` | heading or paragraph |
| `image` | `src` | single full-width image (lazy) |
| `grid` (a.k.a. `photo-grid`) | `items: [{src}]` | Behance flex row — images share a height, widths proportional to aspect ratio, no gaps; equalized on load |
| `video` | `embedUrl` | responsive iframe; detects vertical (reel) vs landscape for height |
| `beforeafter` | `before`, `after`, `labelBefore`, `labelAfter` | draggable before/after slider |
| `separator` (a.k.a. `sep`) | — | thin gradient divider |

**Editor** (`editor.html`, opened per project): add blocks (text / image / grid / video / beforeafter / sep),
reorder, edit each block's fields, upload images per block. Saves via `/api/projects/<id>/modules`.

---

## 4. Lightboxes / players
### Image lightbox
Full-screen; prev/next nav; close. Fed by the current gallery (detail page images or grid module items).

### Reel / Video player (`openVideoLightbox` → reel lightbox)
Instagram-style **vertical 9:16** player:
- Builds a list of all video projects; plays the selected one.
- Swipe up/down (or nav buttons) to move between reels; tap zones on the sides.
- Mute/unmute (remembers unmute choice); autoplay.
- Supports YouTube / Vimeo / direct embeds (provider detection for icon/badge).

---

## 5. Highlights (above the projects grid)
Story circles (from `settings.highlights`) rendered above the projects section. Click → a **9:16 story viewer**:
- Progress-bar segments per media item at the top.
- Images auto-advance (~4.5s); videos play to end then advance.
- Tap left = previous, tap right = next; advances to the next highlight automatically; close button.
- Media served from R2/CDN; thumbnails used for the circle covers.

---

## Rebuild notes for Next.js + Payload
- **`modules` maps directly to a Payload `blocks` field** — define block types: text, image, grid (array of images), video, beforeafter, separator. This is Payload's native page-builder.
- `images[]` → an array/upload-relationship field.
- `project_type` → a select controlling which detail layout the frontend renders.
- The grid/reel/story players are **client components (islands)** — reuse the exact interaction rules above.
- Keep the WebP thumbnail convention (`<name>_t.webp`) so grids stay light, or use Payload/Next image resizing (imageSizes) to generate equivalents.
