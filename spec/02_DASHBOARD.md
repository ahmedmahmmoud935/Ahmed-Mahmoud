# ViralPX — Client Dashboard (`/admin`) — full spec

> The client editor. A left sidebar with tabs; each tab edits part of the portfolio.
> Language toggle (AR/EN) at top. Mobile: sidebar becomes a slide-in drawer + a back button.
> All data saves to the `settings` store or the relational tables via the APIs in `04_API.md`.
> **Priority area** — describe/rebuild faithfully.

## Sidebar tabs (in order)
`projects · highlights · analytics · categories · design · sections · navbar · mobilebar · content · logos · achievements · testimonials · articles · social` — plus **users** (owner only).

Each tab loads its data on open. Switching tabs closes any open modal. Tab state is pushed to
history (browser back returns to previous tab, not a full reload).

---

## 1. Projects
The core content type. List of the client's projects with thumbnail, title, category, date, actions (edit/delete).
- **Filter tabs**: Designs (images) / Reels (9:16 video) / Videos (16:9). Which tabs show is controlled by `proj_tabs`.
- **Category filter** within each.
- **Drag to reorder** (saves `sort_order` via `/api/projects/reorder`).
- **Add/Edit project** opens a full editor (see `03_PROJECTS_DISPLAY.md` → "Project editor"). Fields:
  - `title`, `category` (from the relevant category list), `description`
  - `media_type`: image | video
  - `cover_url` (uploaded), for video also `video_url` (embed link) + `video_kind` (reel|video) + `aspect_ratio`
  - `project_type`: **grid** (image gallery), **free** (module page-builder / Behance-style), **stacked** (cover + images)
  - `images[]` (gallery) and/or `modules[]` (page builder blocks)
- **Import tools**: proxy-image / bookmarklet / Vimeo fetch / video thumbnail — import media from external URLs (Behance etc.). See API.

## 2. Highlights (Instagram-style)
List of highlights; add/edit modal:
- `title_ar`, `title_en`, circular `cover_url` (upload)
- **Media items**: add multiple images and/or a video (uploaded). Each `{type:'image'|'video', url}`.
- First item auto-used as cover if none set. Delete items.
- Saved to `settings.highlights`. Rendered on the portfolio as story circles above the projects grid, opening a 9:16 story viewer.

## 3. Analytics
Read-only dashboard from `/api/analytics?days=N`. Shows:
- **Stat cards**: total_visits, unique_visitors
- **Devices** breakdown (desktop/mobile/tablet)
- **Top projects** (most viewed)
- **Referrers**
- Country names + device icons are mapped client-side. Range selector (e.g. 7/30/all days).

## 4. Categories
Two editable lists: **image categories** and **reel/video categories**. Add (text input + button),
delete, per list. Saved to `settings.image_categories` / `settings.video_categories`. These populate
the category filters on projects and the public portfolio.

## 5. Design (large tab)
The visual customization. Sub-areas:
- **Theme switcher**: cards for each theme (currently `default` = fully custom, and `kinetic` = animated — kinetic being retired/cleaned). Selecting a theme can preset the layout/font/bg choices; a per-theme override snapshot is kept (`theme_overrides[themeId]`), and `_custom_<key>` flags mark fields the user changed so the preset won't clobber them.
- **Component shapes** (`theme_config.components`): card `solid|glass|outline`, navbar `blur|solid|transparent`, button `rounded|sharp|pill`. Radio pickers with a live highlight.
- **Smart color palettes**: click-to-apply presets. Plus manual color pickers for `colors.{accent,bg,bg2,text,subtext}`.
- **Background**: preset (`dark|ocean|sunset|forest|mono|pearl`) or custom `type solid|gradient` + two colors.
- **Layouts** (each a radio group):
  - hero: `centered | split | massive | cover-full | minimal`
  - about: `classic | visual | simple`
  - projects: `grid | masonry | list | freegrid`
  - contact: `classic | split`
  - skills: `tags | inline | bars`  · tools: `classic | compact`  · experience: `classic | timeline`
- **Typography** `style_font`: `default | modern | editorial | elegant | bold` (each is an AR+EN Google-font pair — see 05).
- **Direction** `style_direction`: `auto | rtl | ltr`
- **Cursor** `style_cursor`: `default | dot-ring`
- **Animations** `style_anim`: `fade-up | fade | none`
- **Hero cover image**: upload + `size (cover/contain/%)`, `position x/y`, `overlay %`, `height vh`.
- Per-theme **reset** button.

## 6. Sections
Drag-and-drop reorder + show/hide toggle for each portfolio section (`sections` array).
Saves order + visibility. Controls what appears on the portfolio and in what order.

## 7. Navbar
Edit the top-nav links (`navbar_links`): label AR/EN + visibility per link. (Articles link is appended automatically.)

## 8. Mobile bar
Editor for the mobile bottom bar (`mobile_bar`): enable toggle + **3 buttons** (left/center/right).
Per button: action `section | whatsapp | articles | link`, target (section id or URL), icon (FA), label AR/EN.
Live preview. Center button is the elevated/prominent one.

## 9. Content
Text editors for each section's copy (the `content` object):
- **Hero**: name, title/role, button1, button2 (all AR+EN)
- **About**: text (AR+EN) + tags (comma list, AR+EN) + about photo (`photo_url`)
- **Expertise/Services**: title + list of service items
- **Experience**: list of jobs (company, role, period, description…)
- **Education**: list of entries
- **Skills**: comma list (AR+EN)
- **Tools**: list of tools (name + icon/uploaded image)
- **Contact**: title, subtitle, email, phone (AR+EN)
Each list supports add/edit/remove rows.

## 10. Logos (clients)
CRUD for client logos (`client_logos` table): name, logo image (upload), website_url, drag-reorder.

## 11. Achievements
CRUD for counters (`achievements` table): title AR + title_en, value (string like "50+"), optional icon, reorder.

## 12. Testimonials
CRUD (`testimonials` table): name, role, company, content, avatar (upload), rating (1-5), approved toggle.
Public visitors can also submit testimonials (rate-limited) → land as `approved=0` for moderation.
There is a public submit page at `/testimonial/<username>`.

## 13. Articles (blog)
CRUD (`articles` table). Editor:
- `title_ar`, `title_en`, `slug` (auto from title, editable), `excerpt_ar`, `excerpt_en`
- `cover_url` (upload)
- **content editor**: rich-text WYSIWYG (bold/italic/headings/lists/links/**image upload**/quote) **and** a raw-HTML toggle. Saved as HTML (`mode='html'`; legacy `markdown` still rendered).
- `tags` (comma), `published` toggle, computed `read_min`.
- Cache-busting on fetch so edits appear immediately.

## 14. Social
- Profile photo (`avatar_url` / `photo_url`) upload.
- Social links: whatsapp, behance, instagram, linkedin, facebook, vimeo (+ visibility list `social_visible`).
- WhatsApp powers the floating button + mobile-bar contact.

## 15. Users (OWNER ONLY)
Manage all clients:
- Create client (username + password), delete, change password.
- Set **storage quota** (`storage_limit_mb`) per client; usage tracked (`storage_used_mb`).
- Assign **custom domain** per client (`domains` table).
- Owner stats overview (`/api/owner/stats`).

---

## Cross-cutting dashboard behaviors to replicate
- **Bilingual UI** with i18n dictionaries; every content field is AR+EN.
- **Uploads** go through `/api/upload` → returns a URL; images auto-converted to WebP + `_t.webp` thumbnail; videos allowed. Storage quota enforced per client.
- **Autosave pattern**: most tabs have a "Save" button that PUTs the whole payload to `/api/settings` (settings) or the relevant collection API.
- **Live-ish**: changes apply on the portfolio after save (no build step in current system).
- **Per-tenant isolation**: every read/write scoped by `user_id` (session). In Payload use access control + a tenant field / the multi-tenant plugin.
