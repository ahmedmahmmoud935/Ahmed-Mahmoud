import os, sqlite3, json, secrets, uuid, re, base64, time, shutil, threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from flask import Flask, request, jsonify, session, send_from_directory, abort, redirect
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')

# ─────────────── SECURITY CONFIG ───────────────
# SECRET_KEY MUST be set as env var in production (Render)
# If missing, generate one but warn — sessions will break on restart
_env_secret = os.environ.get('SECRET_KEY')
if not _env_secret:
    print("⚠️  WARNING: SECRET_KEY not set in environment! Using random key — all sessions will be lost on restart.")
    print("⚠️  Set SECRET_KEY env var in Render for production.")
    _env_secret = secrets.token_hex(32)
app.secret_key = _env_secret

# Session cookie hardening
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # JS can't read the cookie (prevents XSS theft)
    SESSION_COOKIE_SAMESITE='Lax',    # prevents CSRF on most cross-site requests
    SESSION_COOKIE_SECURE=os.environ.get('RENDER', '') == 'true',  # HTTPS-only on Render
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

CORS(app, supports_credentials=True)

# gzip compression for HTML/CSS/JS/JSON (huge speed boost on slow networks)
try:
    from flask_compress import Compress
    app.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'text/javascript',
                                         'application/javascript', 'application/json',
                                         'image/svg+xml']
    app.config['COMPRESS_LEVEL'] = 6
    app.config['COMPRESS_MIN_SIZE'] = 500
    Compress(app)
    print("[OK] gzip compression enabled")
except ImportError:
    print("[WARN] flask-compress not installed - responses wont be gzipped")

DB_PATH    = '/var/data/portfolio.db'
UPLOAD_DIR = '/var/data/uploads'
BACKUP_DIR = '/var/data/backups'
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin123')

# ─────────────── RATE LIMITING ───────────────
# Track login attempts per IP: {ip: deque of timestamps}
_login_attempts = defaultdict(lambda: deque(maxlen=20))
LOGIN_MAX_ATTEMPTS = 5          # max 5 attempts
LOGIN_WINDOW = 15 * 60          # per 15 minutes
LOGIN_LOCKOUT = 30 * 60         # lock for 30 minutes after exceeding

def check_rate_limit(ip):
    """Returns (allowed: bool, wait_seconds: int)"""
    now = time.time()
    attempts = _login_attempts[ip]
    # drop attempts outside window
    while attempts and (now - attempts[0] > LOGIN_WINDOW):
        attempts.popleft()
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        oldest = attempts[0]
        wait = int(LOGIN_LOCKOUT - (now - oldest))
        if wait > 0:
            return False, wait
        attempts.clear()
    return True, 0

def record_failed_login(ip):
    _login_attempts[ip].append(time.time())

def reset_login_attempts(ip):
    _login_attempts[ip].clear()

# ─────────────── AUTO BACKUP ───────────────
def auto_backup_db():
    """Run every 6 hours, keep last 7 backups."""
    def _loop():
        while True:
            try:
                if os.path.exists(DB_PATH):
                    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = os.path.join(BACKUP_DIR, f'portfolio_{stamp}.db')
                    shutil.copy2(DB_PATH, backup_path)
                    # Keep only last 7 backups
                    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
                    while len(backups) > 7:
                        try: os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
                        except: pass
                    print(f"✅ Database backup: {backup_path}")
            except Exception as e:
                print(f"⚠️ Backup failed: {e}")
            time.sleep(6 * 60 * 60)  # every 6 hours
    threading.Thread(target=_loop, daemon=True).start()

auto_backup_db()

# ─────────────────────────── DB ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

DEFAULT_SECTIONS = json.dumps([
    {"id":"hero",       "label_ar":"الرئيسية",       "label_en":"Hero",          "visible":True,  "order":0},
    {"id":"about",      "label_ar":"عن النفس",        "label_en":"About",         "visible":True,  "order":1},
    {"id":"expertise",  "label_ar":"الخدمات",         "label_en":"Key Expertise", "visible":True,  "order":2},
    {"id":"education",  "label_ar":"التعليم",          "label_en":"Education",     "visible":True,  "order":3},
    {"id":"skills",     "label_ar":"المهارات",         "label_en":"Skills",        "visible":True,  "order":4},
    {"id":"tools",      "label_ar":"الأدوات",          "label_en":"Tools",         "visible":True,  "order":5},
    {"id":"experience", "label_ar":"الخبرات",          "label_en":"Experience",    "visible":True,  "order":6},
    {"id":"projects",   "label_ar":"المشاريع",         "label_en":"Projects",      "visible":True,  "order":7},
    {"id":"contact",    "label_ar":"تواصل معي",        "label_en":"Contact",       "visible":True,  "order":8}
])

DEFAULT_COLORS = json.dumps({
    "accent":   "#F97316",
    "bg":       "#0A0A0A",
    "bg2":      "#111111",
    "text":     "#FFFFFF",
    "subtext":  "#999999"
})

DEFAULT_CONTENT = json.dumps({
    "hero": {
        "name_en": "Ahmed Mahmoud",
        "name_ar": "أحمد محمود",
        "title_en": "Graphic Designer",
        "title_ar": "مصمم جرافيك",
        "btn1_en": "View Work", "btn1_ar": "أعمالي",
        "btn2_en": "Get In Touch", "btn2_ar": "تواصل معي"
    },
    "about": {
        "text_en": "I'm a passionate Graphic Designer with years of experience in branding, social media design, and visual identity. I craft meaningful visual experiences that connect brands with their audience.",
        "text_ar": "أنا مصمم جرافيك متحمس بسنوات من الخبرة في الهوية البصرية وتصميم السوشيال ميديا. أصنع تجارب بصرية تربط العلامات التجارية بجمهورها.",
        "tags_en": "Brand Identity,Social Media,Typography,Print Design,Motion Graphics",
        "tags_ar": "هوية بصرية,سوشيال ميديا,تايبوغرافي,تصميم مطبوعات,موشن جرافيك"
    },
    "education": {
        "items": json.dumps([
            {"degree_en":"Faculty of Fine Arts","degree_ar":"كلية الفنون الجميلة","school_en":"Abu Dhams University","school_ar":"جامعة أبو دهمس","years":"2018–2022"}
        ])
    },
    "skills": {
        "items_en": "Creative Thinking,Communication,Team Work,Creativity,Time Management,Problem Solving,Adaptability,Presentation,Typography Skills,Leadership",
        "items_ar": "تفكير إبداعي,تواصل,عمل جماعي,إبداع,إدارة الوقت,حل المشكلات,تكيّف,عروض تقديمية,مهارات تايبوغرافي,قيادة"
    },
    "tools": {
        "items": json.dumps([
            {"name":"Photoshop","icon":"fa-brands fa-adobe"},
            {"name":"Illustrator","icon":"fa-solid fa-vector-square"},
            {"name":"Premiere Pro","icon":"fa-solid fa-film"},
            {"name":"InDesign","icon":"fa-solid fa-layer-group"},
            {"name":"Figma","icon":"fa-brands fa-figma"},
            {"name":"After Effects","icon":"fa-solid fa-wand-magic-sparkles"}
        ])
    },
    "experience": {
        "items": json.dumps([
            {"company_en":"Casftime Group","company_ar":"مجموعة كاسفتايم","role_en":"Senior Graphic Designer","role_ar":"مصمم جرافيك أول","years":"2023 – Present"},
            {"company_en":"Creative Canvas","company_ar":"كانفاس الإبداعي","role_en":"Graphic Designer","role_ar":"مصمم جرافيك","years":"2021 – 2023"},
            {"company_en":"Ty Print Agency","company_ar":"وكالة تي برينت","role_en":"Junior Designer","role_ar":"مصمم مبتدئ","years":"2019 – 2021"}
        ])
    },
    "expertise": {
        "title_en": "Key Expertise", "title_ar": "خدماتي",
        "items": json.dumps([
            {"title_en":"Graphic Design","title_ar":"تصميم جرافيك","icon":"fa-solid fa-pen-nib","points_en":"Designing creative visuals for social media platforms.|Print design, including packaging, brochures, menus, and company profiles.","points_ar":"تصميم مرئيات إبداعية لمنصات السوشيال ميديا.|تصميم مطبوعات تشمل التغليف والكتيبات والمطاعم وبروفايلات الشركات."},
            {"title_en":"Brand Identity","title_ar":"هوية بصرية","icon":"fa-solid fa-layer-group","points_en":"Creating complete visual identities for brands.|Logo design, color palettes, and brand guidelines.","points_ar":"إنشاء هويات بصرية متكاملة للعلامات التجارية.|تصميم شعارات وألوان وأدلة العلامة التجارية."},
            {"title_en":"Social Media","title_ar":"سوشيال ميديا","icon":"fa-brands fa-instagram","points_en":"Managing and designing content for social platforms.|Creating engaging posts, stories, and campaigns.","points_ar":"إدارة وتصميم محتوى لمنصات التواصل الاجتماعي.|إنشاء منشورات وستوريز وحملات جذابة."},
            {"title_en":"Motion Graphics","title_ar":"موشن جرافيك","icon":"fa-solid fa-film","points_en":"Creating animated graphics and video content.|Motion design for social media and presentations.","points_ar":"إنشاء جرافيك متحرك ومحتوى فيديو.|تصميم موشن للسوشيال ميديا والعروض التقديمية."}
        ])
    },
    "projects": {
        "title_en": "Selected Work", "title_ar": "أعمال مختارة",
        "subtitle_en": "A collection of projects I've had the pleasure of working on",
        "subtitle_ar": "مجموعة من المشاريع التي عملت عليها"
    },
    "contact": {
        "title_en": "Let's Work Together", "title_ar": "لنعمل معاً",
        "subtitle_en": "Have a project in mind? I'd love to hear about it.",
        "subtitle_ar": "لديك مشروع؟ أحب أسمع عنه.",
        "email": "", "phone": ""
    }
})

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                category    TEXT NOT NULL,
                description TEXT DEFAULT '',
                media_type  TEXT DEFAULT 'image',
                cover_url   TEXT DEFAULT NULL,
                video_url   TEXT DEFAULT NULL,
                sort_order  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                project_type TEXT DEFAULT 'grid',
                modules     TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS project_images (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                url        TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            -- migration: add new cols if missing
            CREATE TABLE IF NOT EXISTS _migrations(id INTEGER PRIMARY KEY);
        ''')
        # Safe migrations
        for col, defval in [('project_type',"'grid'"), ('modules',"'[]'")]:
            try:
                db.execute(f'ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {defval}')
                db.commit()
            except: pass
        defaults = [
            ('whatsapp',''),('behance',''),('instagram',''),('linkedin',''),('facebook',''),('vimeo',''),
            ('social_visible', json.dumps(['whatsapp','behance','instagram','linkedin','vimeo'])),
            ('photo_url',''),('hero_cover_url',''),
            ('video_cols','4'),('image_cols','4'),
            ('video_cols_mobile','2'),('video_cols_tablet','3'),('video_cols_desktop','4'),
            ('image_cols_mobile','2'),('image_cols_tablet','3'),('image_cols_desktop','4'),
            ('vimeo_token',''),
            ('hero_cover_size','cover'),     # cover | contain | <number>%
            ('hero_cover_pos_x','50'),       # 0-100
            ('hero_cover_pos_y','50'),       # 0-100
            ('hero_cover_overlay','55'),     # 0-100 darkness
            ('image_categories', json.dumps([
                'Social Media','Brand Identity','Logo Design','Print Design','Packaging','Posters','UI/UX'
            ])),
            ('video_categories', json.dumps([
                'Reels','Motion Graphics','Video Editing','AI Videos','Promo Ads','Tutorials'
            ])),
            ('navbar_links', json.dumps([
                {"id":"about",      "label_ar":"عن النفس",  "label_en":"About",      "visible":True},
                {"id":"expertise",  "label_ar":"الخدمات",   "label_en":"Services",   "visible":True},
                {"id":"experience", "label_ar":"الخبرات",   "label_en":"Experience", "visible":True},
                {"id":"projects",   "label_ar":"المشاريع",  "label_en":"Projects",   "visible":True},
                {"id":"contact",    "label_ar":"تواصل",     "label_en":"Contact",    "visible":True},
            ])),
            ('colors',   DEFAULT_COLORS),
            ('sections', DEFAULT_SECTIONS),
            ('content',  DEFAULT_CONTENT),
        ]
        for k, v in defaults:
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))
        db.commit()

init_db()

# Load saved credentials from DB (override env defaults if changed via UI)
def _load_creds():
    global ADMIN_USER, ADMIN_PASS
    try:
        db = get_db()
        u = db.execute("SELECT value FROM settings WHERE key='admin_user'").fetchone()
        p = db.execute("SELECT value FROM settings WHERE key='admin_pass'").fetchone()
        if u and u['value']: ADMIN_USER = u['value']
        if p and p['value']: ADMIN_PASS = p['value']
    except: pass
_load_creds()

# ─────────────────────────── AUTH ────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/auth/login', methods=['POST'])
def login():
    # Rate limit: get client IP (handle proxy headers)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    allowed, wait = check_rate_limit(ip)
    if not allowed:
        mins = wait // 60 + 1
        return jsonify({'error': f'محاولات كثيرة جداً — حاول بعد {mins} دقيقة'}), 429

    d = request.get_json() or {}
    # Refresh creds from DB in case they were changed
    _load_creds()
    if d.get('username') == ADMIN_USER and d.get('password') == ADMIN_PASS:
        session['logged_in'] = True
        session.permanent = True
        reset_login_attempts(ip)
        return jsonify({'ok': True})

    # Failed login — track it
    record_failed_login(ip)
    remaining = LOGIN_MAX_ATTEMPTS - len(_login_attempts[ip])
    msg = 'بيانات غير صحيحة'
    if 0 < remaining <= 2:
        msg += f' — متبقي {remaining} محاولة'
    return jsonify({'error': msg}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear(); return jsonify({'ok': True})

@app.route('/api/auth/check')
def auth_check():
    return jsonify({'logged_in': bool(session.get('logged_in'))})

# ─────────────────────────── FILES ───────────────────────────────────────────
ALLOWED_IMG = {'jpg','jpeg','png','gif','webp'}
ALLOWED_VID = {'mp4','mov','webm','avi'}

# Allow up to 100MB request bodies (cover image + gallery in base64 can be huge)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'الملف كبير جداً — حاول ضغط الصور'}), 413

def save_dataurl(dataurl, allowed_exts):
    if not dataurl or not isinstance(dataurl, str):
        return None
    m = re.match(r'data:([^;]+);base64,(.+)', dataurl, re.DOTALL)
    if not m: return None
    mime, b64 = m.group(1), m.group(2)
    ext = {'image/jpeg':'jpg','image/jpg':'jpg','image/png':'png','image/gif':'gif','image/webp':'webp',
           'image/heic':'jpg','image/heif':'jpg',  # treat HEIC as jpg (browser usually converts)
           'video/mp4':'mp4','video/quicktime':'mov','video/webm':'webm','video/avi':'avi'}.get(mime.lower(),'bin')
    if ext not in allowed_exts: return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        with open(fpath, 'wb') as f:
            f.write(base64.b64decode(b64))
        # Optimize images (not videos)
        if ext in ('jpg','jpeg','png','webp'):
            optimize_image(fpath)
        return f"/uploads/{fname}"
    except Exception as e:
        print(f"save_dataurl error: {e}")
        return None

# Optional image optimization (graceful fallback if Pillow unavailable)
try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️ Pillow not installed — images won't be optimized")

def optimize_image(filepath, max_dim=1920, quality=85):
    """Optimize image + create WebP version + create 600px thumbnail.
    Generates 3 files for each upload:
      - filename.ext        -> optimized original (max 1920px, q=85)
      - filename.webp       -> WebP version (~60% smaller, same quality)
      - filename.thumb.webp -> 600px thumbnail for grid display (~95% smaller)
    Returns True if successful."""
    if not HAS_PIL: return False
    try:
        ext = filepath.rsplit('.', 1)[-1].lower()
        if ext in ('gif', 'svg'): return False
        img = Image.open(filepath)
        img = ImageOps.exif_transpose(img)
        # Convert palette/RGBA to suitable mode
        if img.mode in ('RGBA', 'P', 'LA'):
            if ext in ('jpg', 'jpeg'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P': img = img.convert('RGBA')
                bg.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                img = bg
            elif ext != 'png':
                img = img.convert('RGB')
        # 1. Optimize original in place
        original = img.copy()
        if original.width > max_dim or original.height > max_dim:
            original.thumbnail((max_dim, max_dim), Image.LANCZOS)
        save_kwargs = {'optimize': True}
        if ext in ('jpg', 'jpeg'):
            save_kwargs.update(quality=quality, progressive=True)
        elif ext == 'webp':
            save_kwargs.update(quality=quality, method=6)
        elif ext == 'png':
            save_kwargs.update(compress_level=7)
        original.save(filepath, **save_kwargs)

        # 2. Create WebP variant (skip if already webp)
        if ext != 'webp':
            webp_path = filepath.rsplit('.', 1)[0] + '.webp'
            webp_img = img.copy()
            if webp_img.width > max_dim or webp_img.height > max_dim:
                webp_img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            if webp_img.mode == 'RGBA':
                webp_img.save(webp_path, 'WEBP', quality=quality, method=6)
            else:
                if webp_img.mode != 'RGB': webp_img = webp_img.convert('RGB')
                webp_img.save(webp_path, 'WEBP', quality=quality, method=6)

        # 3. Create thumbnail (600px wide WebP) for grid display
        thumb_path = filepath.rsplit('.', 1)[0] + '.thumb.webp'
        thumb = img.copy()
        thumb.thumbnail((600, 600), Image.LANCZOS)
        if thumb.mode not in ('RGB', 'RGBA'):
            thumb = thumb.convert('RGB')
        thumb.save(thumb_path, 'WEBP', quality=78, method=6)

        return True
    except Exception as e:
        print(f"optimize_image error for {filepath}: {e}")
        return False

# Direct file upload endpoint — returns URL immediately so admin doesn't need base64 in save body
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'لا يوجد ملف'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'اسم الملف فارغ'}), 400
    kind = request.form.get('kind', 'image')
    allowed = ALLOWED_VID if kind == 'video' else ALLOWED_IMG
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    # Normalize heic/heif to jpg (Safari often sends these)
    if ext in ('heic', 'heif'):
        ext = 'jpg'
    if ext not in allowed:
        return jsonify({'error': f'نوع غير مسموح: {ext}'}), 400
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        f.save(fpath)
        # Optimize images (skip videos)
        if kind != 'video':
            optimize_image(fpath)
        return jsonify({'url': f"/uploads/{fname}"})
    except Exception as e:
        return jsonify({'error': f'فشل الحفظ: {str(e)}'}), 500

def delete_file(url):
    if url and url.startswith('/uploads/'):
        p = os.path.join(UPLOAD_DIR, os.path.basename(url))
        # Delete original + webp variant + thumbnail variant
        base = p.rsplit('.', 1)[0]
        for variant in [p, base + '.webp', base + '.thumb.webp']:
            try:
                if os.path.exists(variant): os.remove(variant)
            except: pass

# ─────────────────────────── PROJECTS ────────────────────────────────────────
def _migrate_modules_base64(mods, pid, db):
    """Convert any lingering base64 data in modules to uploaded URLs. Returns (new_mods, changed)."""
    changed = False
    out = []
    for mod in mods or []:
        if not isinstance(mod, dict):
            out.append(mod); continue
        mod = dict(mod)
        mtype = mod.get('type')
        if mtype == 'image':
            src = mod.get('src', '')
            if isinstance(src, str) and src.startswith('data:'):
                url = save_dataurl(src, ALLOWED_IMG)
                if url:
                    mod['src'] = url
                    changed = True
        elif mtype in ('photo-grid', 'grid'):
            new_items = []
            for item in mod.get('items', []) or []:
                if isinstance(item, dict):
                    item = dict(item)
                    s = item.get('src', '')
                    if isinstance(s, str) and s.startswith('data:'):
                        url = save_dataurl(s, ALLOWED_IMG)
                        if url:
                            item['src'] = url
                            changed = True
                new_items.append(item)
            mod['items'] = new_items
        out.append(mod)
    if changed:
        try:
            db.execute('UPDATE projects SET modules=? WHERE id=?', (json.dumps(out), pid))
            db.commit()
        except: pass
    return out

def project_to_dict(row, db):
    imgs = db.execute('SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order',(row['id'],)).fetchall()
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    # Auto-migrate old base64 data (one-time heal)
    mods = _migrate_modules_base64(mods, row['id'], db)
    return {'id':row['id'],'title':row['title'],'category':row['category'],
            'description':row['description'] or '','mediaType':row['media_type'],
            'coverImage':row['cover_url'],'videoUrl':row['video_url'],
            'images':[r['url'] for r in imgs],'date':row['created_at'][:10],
            'projectType': row['project_type'] or 'grid',
            'modules': mods}

# ── Modules (Behance editor) ──
@app.route('/api/projects/<int:pid>/modules', methods=['GET'])
@login_required
def get_modules(pid):
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: abort(404)
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    return jsonify({'modules': mods, 'project': project_to_dict(row, db)})

@app.route('/api/projects/<int:pid>/modules', methods=['PUT'])
@login_required
def save_modules(pid):
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: abort(404)
    d = request.get_json()
    modules = d.get('modules', [])
    project_type = d.get('projectType', row['project_type'] or 'grid')

    # Process module media uploads
    processed = []
    for mod in modules:
        mod = dict(mod)
        mtype = mod.get('type')
        # image module — save if base64
        if mtype == 'image' and mod.get('src','').startswith('data:'):
            url = save_dataurl(mod['src'], ALLOWED_IMG)
            mod['src'] = url or mod['src']
        # photo-grid / grid module — save each image (editor uses 'grid')
        if mtype in ('photo-grid', 'grid'):
            new_items = []
            for item in mod.get('items', []) or []:
                item = dict(item) if isinstance(item, dict) else {}
                src = item.get('src', '') if isinstance(item, dict) else ''
                if src and src.startswith('data:'):
                    url = save_dataurl(src, ALLOWED_IMG)
                    item['src'] = url or src
                new_items.append(item)
            mod['items'] = new_items
        processed.append(mod)

    db.execute('UPDATE projects SET modules=?, project_type=? WHERE id=?',
               (json.dumps(processed), project_type, pid))

    # For grid type via editor: sync gallery (project_images) from modules, KEEP cover_url intact
    if project_type == 'grid' and processed:
        img_modules = [m for m in processed if m.get('type') == 'image' and m.get('src')]
        if img_modules:
            # Gallery = all image modules (cover stays separate)
            db.execute('DELETE FROM project_images WHERE project_id=?', (pid,))
            for i, m in enumerate(img_modules):
                db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',
                           (pid, m['src'], i))

    db.commit()
    return jsonify({'ok': True, 'modules': processed})

@app.route('/admin/editor/<int:pid>')
def project_editor_page(pid):
    if not session.get('logged_in'):
        return redirect('/admin')
    return send_from_directory(app.static_folder, 'editor.html')

@app.route('/api/projects/reorder', methods=['PUT'])
@login_required
def reorder_projects():
    ids = request.get_json().get('ids', [])
    db  = get_db()
    for i, pid in enumerate(ids):
        db.execute('UPDATE projects SET sort_order=? WHERE id=?', (len(ids)-i, pid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/projects')
def get_projects():
    db = get_db()
    rows = db.execute('SELECT * FROM projects ORDER BY sort_order DESC, id DESC').fetchall()
    return jsonify([project_to_dict(r,db) for r in rows])

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    d = request.get_json()
    title = (d.get('title') or '').strip()
    if not title: return jsonify({'error':'العنوان مطلوب'}),400
    # Accept either data URL or pre-uploaded URL for cover
    cov = d.get('coverImage')
    if cov and cov.startswith('data:'):
        cover_url = save_dataurl(cov, ALLOWED_IMG)
    elif cov and cov.startswith('/uploads/'):
        cover_url = cov
    else:
        cover_url = None
    # embedUrl takes priority over file upload for video
    embed_url = d.get('embedUrl')
    if embed_url:
        video_url = embed_url
    else:
        vd = d.get('videoData')
        if vd and vd.startswith('data:'):
            video_url = save_dataurl(vd, ALLOWED_VID)
        elif vd and vd.startswith('/uploads/'):
            video_url = vd
        else:
            video_url = None
    db = get_db()
    cur = db.execute('INSERT INTO projects(title,category,description,media_type,cover_url,video_url,project_type) VALUES(?,?,?,?,?,?,?)',
        (title,d.get('category','Social Media'),d.get('description',''),d.get('mediaType','image'),cover_url,video_url,d.get('projectType','grid')))
    pid = cur.lastrowid
    for i,img in enumerate(d.get('images',[])):
        if img.startswith('data:'):
            url = save_dataurl(img, ALLOWED_IMG)
        elif img.startswith('/uploads/'):
            url = img
        else:
            url = None
        if url: db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',(pid,url,i))
    db.commit()
    return jsonify(project_to_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(),db)),201

@app.route('/api/projects/<int:pid>', methods=['PUT'])
@login_required
def update_project(pid):
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: abort(404)
    d = request.get_json()

    def resolve_file(field, old_url, allowed):
        v = d.get(field)
        if v is None:   return old_url
        if v == '':     delete_file(old_url); return None
        if v.startswith('data:'): delete_file(old_url); return save_dataurl(v, allowed)
        # Already uploaded URL (pre-uploaded via /api/upload)
        if v.startswith('/uploads/'):
            if v != old_url:
                delete_file(old_url)
            return v
        return old_url

    cover_url = resolve_file('coverImage', row['cover_url'], ALLOWED_IMG)
    # embedUrl takes priority
    if d.get('embedUrl'):
        # delete old file-based video if switching to embed
        if row['video_url'] and not row['video_url'].startswith('http'):
            delete_file(row['video_url'])
        video_url = d['embedUrl']
    else:
        video_url = resolve_file('videoData', row['video_url'], ALLOWED_VID)
    db.execute('UPDATE projects SET title=?,category=?,description=?,media_type=?,cover_url=?,video_url=? WHERE id=?',
        ((d.get('title') or row['title']).strip(), d.get('category',row['category']),
         d.get('description',row['description']), d.get('mediaType',row['media_type']),
         cover_url, video_url, pid))

    # Update project_type if provided
    if 'projectType' in d:
        db.execute('UPDATE projects SET project_type=? WHERE id=?', (d['projectType'], pid))

    keep = d.get('keepImages') or []
    new_imgs = d.get('images') or []
    if 'keepImages' in d or 'images' in d:
        old = db.execute('SELECT url FROM project_images WHERE project_id=?',(pid,)).fetchall()
        kept = set(keep)
        for o in old:
            if o['url'] not in kept: delete_file(o['url'])
        db.execute('DELETE FROM project_images WHERE project_id=?',(pid,))
        for i,url in enumerate(keep):
            db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',(pid,url,i))
        for i,img in enumerate(new_imgs):
            if not img: continue
            if img.startswith('data:'):
                url = save_dataurl(img, ALLOWED_IMG)
            elif img.startswith('/uploads/'):
                url = img  # already uploaded
            else:
                url = None
            if url: db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',(pid,url,len(keep)+i))

    # For grid projects: sync modules array from GALLERY ONLY (cover is separate, stays in cover_url)
    ptype = d.get('projectType', row['project_type'] or 'grid')
    if ptype == 'grid' and d.get('mediaType','image') != 'video':
        imgs = db.execute('SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order',(pid,)).fetchall()
        mods = [{'type':'image','src':r['url']} for r in imgs if r['url']]
        db.execute('UPDATE projects SET modules=? WHERE id=?', (json.dumps(mods), pid))

    db.commit()
    return jsonify(project_to_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(),db))

@app.route('/api/projects/<int:pid>', methods=['DELETE'])
@login_required
def delete_project(pid):
    db = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: abort(404)
    delete_file(row['cover_url']); delete_file(row['video_url'])
    for img in db.execute('SELECT url FROM project_images WHERE project_id=?',(pid,)).fetchall():
        delete_file(img['url'])
    db.execute('DELETE FROM projects WHERE id=?',(pid,)); db.commit()
    return jsonify({'ok':True})

# ─────────────────────────── SETTINGS ────────────────────────────────────────
@app.route('/api/settings')
def get_settings():
    db   = get_db()
    rows = db.execute('SELECT key,value FROM settings').fetchall()
    out  = {}
    for r in rows:
        try:    out[r['key']] = json.loads(r['value'])
        except: out[r['key']] = r['value']
    return jsonify(out)

@app.route('/api/settings', methods=['PUT'])
@login_required
def update_settings():
    d  = request.get_json()
    db = get_db()

    # handle image uploads
    for upload_key, store_key in [('photo_upload','photo_url'), ('hero_cover_upload','hero_cover_url')]:
        img = d.pop(upload_key, None)
        if img and isinstance(img, str) and img.startswith('data:'):
            old = db.execute(f"SELECT value FROM settings WHERE key='{store_key}'").fetchone()
            if old and old['value']: delete_file(old['value'])
            url = save_dataurl(img, ALLOWED_IMG)
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(store_key, url or ''))
        elif img and isinstance(img, str) and img.startswith('/uploads/'):
            # Pre-uploaded via /api/upload — accept the URL directly
            old = db.execute(f"SELECT value FROM settings WHERE key='{store_key}'").fetchone()
            if old and old['value'] and old['value'] != img:
                delete_file(old['value'])
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(store_key, img))
        elif img == '':
            old = db.execute(f"SELECT value FROM settings WHERE key='{store_key}'").fetchone()
            if old and old['value']: delete_file(old['value'])
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(store_key, ''))

    # handle tool image uploads (tool_img_upload_0, tool_img_upload_1, ...)
    tool_img_uploads = {k:v for k,v in d.items() if k.startswith('tool_img_upload_')}
    for key in tool_img_uploads:
        d.pop(key)
    # these are returned separately and merged client-side, but we save them as named keys
    for key, img in tool_img_uploads.items():
        if img and img.startswith('data:'):
            url = save_dataurl(img, ALLOWED_IMG)
            if url:
                db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key.replace('upload','url'), url))
        elif img == '':
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key.replace('upload','url'), ''))

    for k, v in d.items():
        val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
        db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k, val))
    db.commit()
    return jsonify({'ok':True})

# ─────────────────────────── IMPORT UTILITIES ────────────────────────────────
import urllib.request, urllib.error, html as html_mod

def fetch_url(url, headers=None, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'} | (headers or {}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace'), r.headers.get_content_type()

@app.route('/api/proxy-image', methods=['POST'])
@login_required
def proxy_image():
    url = (request.get_json() or {}).get('url','').strip()
    if not url or not url.startswith('http'):
        return jsonify({'error':'invalid url'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            ct   = resp.headers.get_content_type() or 'image/jpeg'
            data = base64.b64encode(resp.read()).decode()
        return jsonify({'dataUrl': f'data:{ct};base64,{data}'})
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500

# ── Vimeo: fetch single video metadata (oEmbed, no auth needed for public) ──
@app.route('/api/vimeo/fetch', methods=['POST'])
@login_required
def vimeo_fetch():
    url = (request.get_json() or {}).get('url','').strip()
    m   = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
    if not m:
        return jsonify({'error':'رابط Vimeo غير صحيح'}), 400
    vid_id = m.group(1)
    try:
        body, _ = fetch_url(f'https://vimeo.com/api/oembed.json?url=https://vimeo.com/{vid_id}&width=640')
        oe = json.loads(body)
        return jsonify({
            'id':          vid_id,
            'title':       oe.get('title',''),
            'description': oe.get('description','') or '',
            'thumbnail':   oe.get('thumbnail_url',''),
            'duration':    oe.get('duration',0),
            'embed_url':   f'https://player.vimeo.com/video/{vid_id}?portrait=0&byline=0&title=0',
        })
    except Exception as ex:
        return jsonify({'error': str(ex)}), 502

# ── Behance: scrape project by URL ──
@app.route('/api/behance/fetch', methods=['POST'])
@login_required
def behance_fetch():
    url = (request.get_json() or {}).get('url','').strip()
    if 'behance.net' not in url:
        return jsonify({'error':'يجب أن يكون رابط Behance'}), 400
    try:
        body, _ = fetch_url(url)
        # Extract title from <title> or og:title
        title = ''
        t = re.search(r'<meta property="og:title"\s+content="([^"]+)"', body)
        if t: title = html_mod.unescape(t.group(1))
        if not title:
            t2 = re.search(r'<title>([^<]+)</title>', body)
            if t2: title = html_mod.unescape(t2.group(1).split('::')[0].strip())

        # Extract description
        desc = ''
        d = re.search(r'<meta property="og:description"\s+content="([^"]+)"', body)
        if d: desc = html_mod.unescape(d.group(1))

        # Extract images — og:image first, then project images
        images = []
        # og:image (cover)
        cover_match = re.search(r'<meta property="og:image"\s+content="([^"]+)"', body)
        cover = html_mod.unescape(cover_match.group(1)) if cover_match else ''

        # All project images from JSON data embedded in page
        # Behance embeds project data as a JS object
        img_urls = []
        # Look for image URLs in the page source
        for m in re.finditer(r'"url"\s*:\s*"(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"]+)"', body):
            u = m.group(1)
            # filter for large images (fs or max_1200)
            if 'fs/' in u or 'max_1200/' in u or 'max_3840/' in u:
                if u not in img_urls: img_urls.append(u)

        # Fallback: any behance project image
        if not img_urls:
            for m in re.finditer(r'(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"\s]+\.(?:jpg|png|jpeg|webp))', body):
                u = m.group(1)
                if u not in img_urls: img_urls.append(u)

        # Proxy the cover and up to 12 images (fetch as base64)
        cover_b64 = ''
        if cover:
            try:
                r2 = proxy_one(cover)
                if r2: cover_b64 = r2
            except: pass

        return jsonify({
            'title':       title,
            'description': desc,
            'cover':       cover,
            'cover_b64':   cover_b64,
            'images':      img_urls[:20],   # send URLs; admin fetches what it wants
        })
    except Exception as ex:
        return jsonify({'error': str(ex)}), 502

def proxy_one(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.behance.net/'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        ct   = resp.headers.get_content_type() or 'image/jpeg'
        data = base64.b64encode(resp.read()).decode()
    return f'data:{ct};base64,{data}'

@app.route('/api/proxy-images', methods=['POST'])
@login_required
def proxy_images():
    """Fetch multiple image URLs and return as base64. Used by Behance import."""
    urls = (request.get_json() or {}).get('urls', [])[:12]
    results = []
    for url in urls:
        try:    results.append(proxy_one(url))
        except: results.append(None)
    return jsonify({'images': results})

# ── Change admin credentials ──
@app.route('/api/auth/credentials', methods=['PUT'])
@login_required
def change_credentials():
    d        = request.get_json() or {}
    new_user = d.get('username','').strip()
    new_pass = d.get('password','').strip()
    old_pass = d.get('old_password','').strip()
    global ADMIN_USER, ADMIN_PASS
    if old_pass != ADMIN_PASS:
        return jsonify({'error':'كلمة المرور الحالية غير صحيحة'}), 403
    if not new_user or not new_pass:
        return jsonify({'error':'أدخل اسم المستخدم وكلمة المرور'}), 400
    if len(new_pass) < 6:
        return jsonify({'error':'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('admin_user', new_user))
    db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('admin_pass', new_pass))
    db.commit()
    ADMIN_USER = new_user
    ADMIN_PASS = new_pass
    return jsonify({'ok': True})

# ─────────────────────────── STATIC ──────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Smart variant selection:
       - ?v=thumb -> serve 600px thumbnail (for grid display, ~95% smaller)
       - Accept: image/webp -> auto-serve WebP variant (~60% smaller)
       - else -> serve original
    """
    variant = request.args.get('v', '').lower()
    base = filename.rsplit('.', 1)[0]
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    target = filename
    # Explicit thumbnail request
    if variant == 'thumb':
        thumb_name = base + '.thumb.webp'
        if os.path.exists(os.path.join(UPLOAD_DIR, thumb_name)):
            target = thumb_name
    # Auto WebP if browser supports it AND it's not a video/animated format
    elif ext not in ('mp4', 'mov', 'webm', 'avi', 'webp', 'gif'):
        accept = request.headers.get('Accept', '')
        if 'image/webp' in accept:
            webp_name = base + '.webp'
            if os.path.exists(os.path.join(UPLOAD_DIR, webp_name)):
                target = webp_name

    response = send_from_directory(UPLOAD_DIR, target)
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['Vary'] = 'Accept'
    return response

@app.route('/admin')
@app.route('/admin.html')
def admin_page():
    return send_from_directory(app.static_folder, 'admin.html')

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    full = os.path.join(app.static_folder, path)
    if path and os.path.exists(full): return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀  http://localhost:{port}   Admin: {ADMIN_USER}/{ADMIN_PASS}")
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV')=='development')
