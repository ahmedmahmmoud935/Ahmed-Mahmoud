#!/usr/bin/env python3
"""
migrate_webp.py — one-time backfill of WebP thumbnails for EXISTING uploads.

Run once (e.g. from the Render Shell):  python migrate_webp.py

For every raster image already in /var/data/uploads it creates:
  - <name>_t.webp   (small thumbnail, <=640px)  ← used by grids/bubbles
  - <name>.webp     (optimized main, <=1920px)  ← available if referenced

Originals are KEPT (nothing is deleted), so existing .jpg/.png URLs keep working.
Safe to re-run: it skips images that already have a thumbnail.
"""
import os, sys

UPLOAD_DIR = os.environ.get('UPLOAD_DIR', '/var/data/uploads')
MAX_DIM, THUMB_DIM, Q = 1920, 640, 82

try:
    from PIL import Image, ImageOps
except Exception:
    print('Pillow not installed — abort.'); sys.exit(1)

RASTER = ('.jpg', '.jpeg', '.png', '.webp')

def main():
    if not os.path.isdir(UPLOAD_DIR):
        print(f'No upload dir at {UPLOAD_DIR}'); return
    files = os.listdir(UPLOAD_DIR)
    done = skipped = failed = 0
    for fn in files:
        lower = fn.lower()
        if not lower.endswith(RASTER):        continue
        if lower.endswith('_t.webp'):          continue          # a thumbnail itself
        stem = fn.rsplit('.', 1)[0]
        thumb = os.path.join(UPLOAD_DIR, stem + '_t.webp')
        if os.path.exists(thumb):              skipped += 1; continue
        src = os.path.join(UPLOAD_DIR, fn)
        try:
            img = ImageOps.exif_transpose(Image.open(src))
            if img.mode == 'P': img = img.convert('RGBA')
            # main webp (only if this file isn't already a .webp)
            if not lower.endswith('.webp'):
                m = img.copy()
                if m.width > MAX_DIM or m.height > MAX_DIM: m.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
                m.save(os.path.join(UPLOAD_DIR, stem + '.webp'), 'WEBP', quality=Q, method=6)
            # thumbnail
            t = img.copy()
            t.thumbnail((THUMB_DIM, THUMB_DIM), Image.LANCZOS)
            t.save(thumb, 'WEBP', quality=78, method=6)
            done += 1
            if done % 25 == 0: print(f'  ...{done} processed')
        except Exception as e:
            failed += 1; print(f'  ! {fn}: {e}')
    print(f'\nDone. created={done}  skipped(existing)={skipped}  failed={failed}')

if __name__ == '__main__':
    main()
