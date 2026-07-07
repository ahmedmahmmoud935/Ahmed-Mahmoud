#!/usr/bin/env python3
"""
migrate_to_r2.py — one-time move of EXISTING local uploads to Cloudflare R2.

Run once from the Render Shell AFTER the R2_* env vars are set:
    python migrate_to_r2.py

What it does (safe + idempotent):
  1. Backs up the SQLite DB first (/var/data/backups/pre_r2_<ts>.db).
  2. Generates any missing WebP thumbnails for existing images.
  3. Uploads EVERY file in /var/data/uploads to R2 (correct content-type + long cache).
  4. Only if all uploads succeed, rewrites every "/uploads/..." URL in the DB to
     "<R2_PUBLIC_URL>/..." across all text columns of all tables.
  5. Local files are KEPT (not deleted) as a rollback safety net.

Re-running is safe: uploads overwrite, and once URLs are rewritten there is no
more "/uploads/" to replace.
"""
import os, sys, sqlite3, shutil, time

DB_PATH    = os.environ.get('DB_PATH', '/var/data/portfolio.db')
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', '/var/data/uploads')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/var/data/backups')

R2_ENDPOINT   = os.environ.get('R2_ENDPOINT', '').rstrip('/')
R2_BUCKET     = os.environ.get('R2_BUCKET', '')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')

if not all([R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY, R2_SECRET_KEY, R2_PUBLIC_URL]):
    print('❌ R2 env vars not set. Set R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID, '
          'R2_SECRET_ACCESS_KEY, R2_PUBLIC_URL first.'); sys.exit(1)

try:
    import boto3
    from botocore.config import Config
except Exception:
    print('❌ boto3 not installed.'); sys.exit(1)

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except Exception:
    HAS_PIL = False

s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT, aws_access_key_id=R2_ACCESS_KEY,
                  aws_secret_access_key=R2_SECRET_KEY, region_name='auto',
                  config=Config(signature_version='s3v4'))

def ctype(k):
    k = k.lower()
    if k.endswith('.webp'): return 'image/webp'
    if k.endswith(('.jpg', '.jpeg')): return 'image/jpeg'
    if k.endswith('.png'): return 'image/png'
    if k.endswith('.gif'): return 'image/gif'
    if k.endswith('.mp4'): return 'video/mp4'
    if k.endswith('.mov'): return 'video/quicktime'
    if k.endswith('.webm'): return 'video/webm'
    return 'application/octet-stream'

IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp')

def gen_thumbs():
    if not HAS_PIL:
        print('  (Pillow missing — skipping thumbnail generation)'); return
    made = 0
    for fn in list(os.listdir(UPLOAD_DIR)):
        low = fn.lower()
        if not low.endswith(IMG_EXT) or low.endswith('_t.webp'): continue
        stem = fn.rsplit('.', 1)[0]
        tp = os.path.join(UPLOAD_DIR, stem + '_t.webp')
        if os.path.exists(tp): continue
        try:
            img = ImageOps.exif_transpose(Image.open(os.path.join(UPLOAD_DIR, fn)))
            if img.mode == 'P': img = img.convert('RGBA')
            img.thumbnail((640, 640), Image.LANCZOS)
            img.save(tp, 'WEBP', quality=78, method=6); made += 1
        except Exception as e:
            print(f'  ! thumb {fn}: {e}')
    print(f'  thumbnails generated: {made}')

def upload_all():
    files = [f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]
    ok = fail = 0
    for i, fn in enumerate(files, 1):
        try:
            s3.upload_file(os.path.join(UPLOAD_DIR, fn), R2_BUCKET, fn, ExtraArgs={
                'ContentType': ctype(fn),
                'CacheControl': 'public, max-age=31536000, immutable'})
            ok += 1
        except Exception as e:
            fail += 1; print(f'  ! upload {fn}: {e}')
        if i % 25 == 0: print(f'  ...{i}/{len(files)} uploaded')
    print(f'  uploaded ok={ok} fail={fail} (total {len(files)})')
    return fail == 0

def rewrite_db():
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    old, new = '/uploads/', R2_PUBLIC_URL + '/'
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    total = 0
    for t in tables:
        cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')]
        for c in cols:
            try:
                cur.execute(
                    f'UPDATE "{t}" SET "{c}"=REPLACE("{c}", ?, ?) '
                    f'WHERE "{c}" LIKE ?', (old, new, '%'+old+'%'))
                if cur.rowcount and cur.rowcount > 0:
                    total += cur.rowcount
                    print(f'  {t}.{c}: {cur.rowcount} rows')
            except Exception:
                pass  # non-text column
    con.commit(); con.close()
    print(f'  DB rows rewritten: {total}')

def main():
    print('▶ Migrating local uploads → R2\n')
    # 1) backup DB
    if os.path.exists(DB_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bk = os.path.join(BACKUP_DIR, f'pre_r2_{time.strftime("%Y%m%d_%H%M%S")}.db')
        shutil.copy2(DB_PATH, bk); print(f'1) DB backed up → {bk}')
    # 2) thumbnails
    print('2) generating missing thumbnails...'); gen_thumbs()
    # 3) upload
    print('3) uploading files to R2...')
    if not os.path.isdir(UPLOAD_DIR):
        print('  no upload dir — nothing to upload'); return
    all_ok = upload_all()
    # 4) rewrite DB only if uploads clean
    if all_ok:
        print('4) rewriting DB URLs → CDN...'); rewrite_db()
        print('\n✅ Done. Old media now served from', R2_PUBLIC_URL)
        print('   (local files kept as backup — safe to delete later once verified)')
    else:
        print('\n⚠️ Some uploads failed — DB NOT rewritten (safe). '
              'Fix the errors above and re-run.')

if __name__ == '__main__':
    main()
