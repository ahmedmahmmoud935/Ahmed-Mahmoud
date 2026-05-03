import os, sqlite3, json, secrets, uuid, re, base64, time, shutil, threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from flask import Flask, request, jsonify, session, send_from_directory, abort, redirect
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')

# ─────────────── SECURITY CONFIG ───────────────
_env_secret = os.environ.get('SECRET_KEY')
if not _env_secret:
    print("⚠️  WARNING: SECRET_KEY not set — sessions will break on restart.")
    _env_secret = secrets.token_hex(32)
app.secret_key = _env_secret

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('RENDER', '') == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

CORS(app, supports_credentials=True)

DB_PATH    = '/var/data/portfolio.db'
UPLOAD_DIR = '/var/data/uploads'
BACKUP_DIR = '/var/data/backups'
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Owner credentials from env (used only to create first owner account)
OWNER_USER = os.environ.get('ADMIN_USER', 'admin')
OWNER_PASS = os.environ.get('ADMIN_PASS', 'admin123')

# ─────────────── RATE LIMITING ───────────────
_login_attempts = defaultdict(lambda: deque(maxlen=20))
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW       = 15 * 60
LOGIN_LOCKOUT      = 30 * 60

def check_rate_limit(ip):
    now = time.time()
    attempts = _login_attempts[ip]
    while attempts and (now - attempts[0] > LOGIN_WINDOW):
        attempts.popleft()
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        wait = int(LOGIN_LOCKOUT - (now - attempts[0]))
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
    def _loop():
        while True:
            try:
                if os.path.exists(DB_PATH):
                    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = os.path.join(BACKUP_DIR, f'portfolio_{stamp}.db')
                    shutil.copy2(DB_PATH, backup_path)
                    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
                    while len(backups) > 7:
                        try: os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
                        except: pass
                    print(f"✅ Backup: {backup_path}")
            except Exception as e:
                print(f"⚠️ Backup failed: {e}")
            time.sleep(6 * 60 * 60)
    threading.Thread(target=_loop, daemon=True).start()

auto_backup_db()

# ─────────────────────────── DB ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

DEFAULT_COLORS = json.dumps({
    "accent":  "#F97316",
    "bg":      "#0A0A0A",
    "bg2":     "#111111",
    "text":    "#FFFFFF",
    "subtext": "#999999"
})

DEFAULT_SECTIONS = json.dumps([
    {"id":"hero",       "label_ar":"الرئيسية",    "label_en":"Hero",          "visible":True, "order":0},
    {"id":"about",      "label_ar":"عن النفس",     "label_en":"About",         "visible":True, "order":1},
    {"id":"expertise",  "label_ar":"الخدمات",      "label_en":"Key Expertise", "visible":True, "order":2},
    {"id":"education",  "label_ar":"التعليم",       "label_en":"Education",     "visible":True, "order":3},
    {"id":"skills",     "label_ar":"المهارات",      "label_en":"Skills",        "visible":True, "order":4},
    {"id":"tools",      "label_ar":"الأدوات",       "label_en":"Tools",         "visible":True, "order":5},
    {"id":"experience", "label_ar":"الخبرات",       "label_en":"Experience",    "visible":True, "order":6},
    {"id":"projects",   "label_ar":"المشاريع",      "label_en":"Projects",      "visible":True, "order":7},
    {"id":"contact",    "label_ar":"تواصل معي",     "label_en":"Contact",       "visible":True, "order":8}
])

DEFAULT_CONTENT = json.dumps({
    "hero": {
        "name_en": "Ahmed Mahmoud", "name_ar": "أحمد محمود",
        "title_en": "Graphic Designer", "title_ar": "مصمم جرافيك",
        "btn1_en": "View Work", "btn1_ar": "أعمالي",
        "btn2_en": "Get In Touch", "btn2_ar": "تواصل معي"
    },
    "about": {
        "text_en": "I'm a passionate Graphic Designer with years of experience.",
        "text_ar": "أنا مصمم جرافيك متحمس بسنوات من الخبرة.",
        "tags_en": "Brand Identity,Social Media,Typography",
        "tags_ar": "هوية بصرية,سوشيال ميديا,تايبوغرافي"
    },
    "education": {"items": json.dumps([])},
    "skills":    {"items_en": "", "items_ar": ""},
    "tools":     {"items": json.dumps([])},
    "experience":{"items": json.dumps([])},
    "expertise": {
        "title_en": "Key Expertise", "title_ar": "خدماتي",
        "items": json.dumps([])
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

DEFAULT_NAVBAR = json.dumps([
    {"id":"about",      "label_ar":"عن النفس", "label_en":"About",      "visible":True},
    {"id":"expertise",  "label_ar":"الخدمات",  "label_en":"Services",   "visible":True},
    {"id":"experience", "label_ar":"الخبرات",  "label_en":"Experience", "visible":True},
    {"id":"projects",   "label_ar":"المشاريع", "label_en":"Projects",   "visible":True},
    {"id":"contact",    "label_ar":"تواصل",    "label_en":"Contact",    "visible":True},
])

DEFAULT_IMAGE_CATS = json.dumps(['Social Media','Brand Identity','Logo Design','Print Design','Packaging','Posters','UI/UX'])
DEFAULT_VIDEO_CATS = json.dumps(['Reels','Motion Graphics','Video Editing','AI Videos','Promo Ads','Tutorials'])

def _default_settings_for_user(user_id, db):
    """Insert default settings for a new user."""
    defaults = [
        ('whatsapp',''), ('behance',''), ('instagram',''), ('linkedin',''),
        ('facebook',''), ('vimeo',''),
        ('social_visible', json.dumps(['whatsapp','behance','instagram','linkedin','vimeo'])),
        ('photo_url',''), ('hero_cover_url',''),
        ('video_cols_mobile','2'), ('video_cols_tablet','3'), ('video_cols_desktop','4'),
        ('image_cols_mobile','2'), ('image_cols_tablet','3'), ('image_cols_desktop','4'),
        ('vimeo_token',''),
        ('hero_cover_size','cover'), ('hero_cover_pos_x','50'), ('hero_cover_pos_y','50'),
        ('hero_cover_overlay','55'), ('hero_height','85'),
        ('brand_logo_url',''), ('favicon_url',''),
        ('image_categories', DEFAULT_IMAGE_CATS),
        ('video_categories', DEFAULT_VIDEO_CATS),
        ('navbar_links', DEFAULT_NAVBAR),
        ('colors',   DEFAULT_COLORS),
        ('sections', DEFAULT_SECTIONS),
        ('content',  DEFAULT_CONTENT),
    ]
    for k, v in defaults:
        db.execute(
            'INSERT OR IGNORE INTO settings(user_id, key, value) VALUES(?,?,?)',
            (user_id, k, v)
        )
    db.commit()

def init_db():
    with get_db() as db:
        # ── Create users table ──
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                username         TEXT UNIQUE NOT NULL,
                password         TEXT NOT NULL,
                storage_limit_mb INTEGER DEFAULT 500,
                storage_used_mb  REAL    DEFAULT 0,
                is_owner         INTEGER DEFAULT 0,
                created_at       TEXT    DEFAULT (datetime('now'))
            );
        ''')

        # ── Ensure owner account exists ──
        owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        if not owner:
            db.execute(
                "INSERT OR IGNORE INTO users(username,password,storage_limit_mb,is_owner) VALUES(?,?,?,1)",
                (OWNER_USER, OWNER_PASS, 10240)   # owner gets 10 GB
            )
            db.commit()
        owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        owner_id = owner['id'] if owner else 1

        # ── Create projects table (with user_id) ──
        db.executescript('''
            CREATE TABLE IF NOT EXISTS projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL DEFAULT 1,
                title        TEXT NOT NULL,
                category     TEXT NOT NULL,
                description  TEXT DEFAULT '',
                media_type   TEXT DEFAULT 'image',
                cover_url    TEXT DEFAULT NULL,
                video_url    TEXT DEFAULT NULL,
                sort_order   INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now')),
                project_type TEXT DEFAULT 'grid',
                modules      TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS project_images (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                url        TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
        ''')

        # ── Migrate projects: add user_id if missing ──
        proj_cols = [r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()]
        if 'user_id' not in proj_cols:
            db.execute(f'ALTER TABLE projects ADD COLUMN user_id INTEGER DEFAULT {owner_id}')
            db.execute(f'UPDATE projects SET user_id={owner_id} WHERE user_id IS NULL OR user_id=0')
            db.commit()

        # Migrate other missing columns in projects
        for col, defval in [('project_type',"'grid'"), ('modules',"'[]'")]:
            if col not in proj_cols:
                try:
                    db.execute(f'ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {defval}')
                    db.commit()
                except: pass

        # ── Settings table: migrate to (user_id, key) if needed ──
        settings_cols = [r[1] for r in db.execute("PRAGMA table_info(settings)").fetchall()]
        if 'user_id' not in settings_cols:
            # settings table exists but has no user_id — migrate it
            try:
                db.executescript(f'''
                    CREATE TABLE IF NOT EXISTS settings_new (
                        user_id INTEGER NOT NULL DEFAULT {owner_id},
                        key     TEXT    NOT NULL,
                        value   TEXT,
                        PRIMARY KEY (user_id, key)
                    );
                    INSERT OR IGNORE INTO settings_new(user_id, key, value)
                        SELECT {owner_id}, key, value FROM settings;
                    DROP TABLE settings;
                    ALTER TABLE settings_new RENAME TO settings;
                ''')
                db.commit()
            except Exception as e:
                print(f"Settings migration error: {e}")
        else:
            # Create fresh settings table if it doesn't exist at all
            db.executescript(f'''
                CREATE TABLE IF NOT EXISTS settings (
                    user_id INTEGER NOT NULL DEFAULT {owner_id},
                    key     TEXT    NOT NULL,
                    value   TEXT,
                    PRIMARY KEY (user_id, key)
                );
            ''')
            db.commit()

        # ── Domains table (custom domain !92 user_id) ──
        db.executescript('''
            CREATE TABLE IF NOT EXISTS domains (
                user_id    INTEGER UNIQUE NOT NULL,
                domain     TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime(''now''))
            );
        ''')
        db.commit()

        # ── Ensure owner has all default settings ──
        _default_settings_for_user(owner_id, db)
        _default_settings_for_user(owner_id, db)

init_db()

# ─────────────────────────── AUTH ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def owner_required(f):
    """Only the owner (is_owner=1) can call this endpoint."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        if not session.get('is_owner'):
            return jsonify({'error': 'ليس لديك صلاحية'}), 403
        return f(*args, **kwargs)
    return decorated

def current_user_id():
    return session.get('user_id', 1)

@app.route('/api/auth/login', methods=['POST'])
def login():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    allowed, wait = check_rate_limit(ip)
    if not allowed:
        mins = wait // 60 + 1
        return jsonify({'error': f'محاولات كثيرة جداً — حاول بعد {mins} دقيقة'}), 429

    d = request.get_json() or {}
    username = d.get('username', '').strip()
    password = d.get('password', '').strip()

    db   = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username=? AND password=?", (username, password)
    ).fetchone()

    if user:
        session['logged_in'] = True
        session['user_id']   = user['id']
        session['is_owner']  = bool(user['is_owner'])
        session['username']  = user['username']
        session.permanent    = True
        reset_login_attempts(ip)
        return jsonify({'ok': True, 'is_owner': bool(user['is_owner']), 'username': user['username']})

    record_failed_login(ip)
    remaining = LOGIN_MAX_ATTEMPTS - len(_login_attempts[ip])
    msg = 'بيانات غير صحيحة'
    if 0 < remaining <= 2:
        msg += f' — متبقي {remaining} محاولة'
    return jsonify({'error': msg}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/check')
def auth_check():
    return jsonify({
        'logged_in': bool(session.get('logged_in')),
        'is_owner':  bool(session.get('is_owner')),
        'username':  session.get('username', ''),
        'user_id':   session.get('user_id'),
    })

# ─────────────────────────── USER MANAGEMENT (owner only) ────────────────────
@app.route('/api/users', methods=['GET'])
@owner_required
def list_users():
    db    = get_db()
    users = db.execute("SELECT id,username,storage_limit_mb,storage_used_mb,is_owner,created_at FROM users ORDER BY id").fetchall()
    return jsonify([dict(u) for u in users])

@app.route('/api/users', methods=['POST'])
@owner_required
def create_user():
    d        = request.get_json() or {}
    username = (d.get('username') or '').strip()
    password = (d.get('password') or '').strip()
    limit_mb = int(d.get('storage_limit_mb', 500))

    if not username or not password:
        return jsonify({'error': 'اسم المستخدم وكلمة المرور مطلوبان'}), 400
    if len(password) < 6:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400

    cur = db.execute(
        "INSERT INTO users(username,password,storage_limit_mb,is_owner) VALUES(?,?,?,0)",
        (username, password, limit_mb)
    )
    db.commit()
    new_user_id = cur.lastrowid

    # Create default settings for the new user
    _default_settings_for_user(new_user_id, db)

    return jsonify({'ok': True, 'id': new_user_id, 'username': username}), 201

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@owner_required
def delete_user(uid):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    if user['is_owner']:
        return jsonify({'error': 'لا يمكن حذف المالك'}), 400

    # Delete user's files
    projects = db.execute("SELECT cover_url,video_url FROM projects WHERE user_id=?", (uid,)).fetchall()
    for p in projects:
        delete_file(p['cover_url'])
        delete_file(p['video_url'])
    imgs = db.execute(
        "SELECT pi.url FROM project_images pi JOIN projects p ON pi.project_id=p.id WHERE p.user_id=?", (uid,)
    ).fetchall()
    for img in imgs:
        delete_file(img['url'])

    db.execute("DELETE FROM projects WHERE user_id=?", (uid,))
    db.execute("DELETE FROM settings WHERE user_id=?", (uid,))
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>/password', methods=['PUT'])
@owner_required
def change_user_password(uid):
    d        = request.get_json() or {}
    new_pass = (d.get('password') or '').strip()
    if len(new_pass) < 6:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400
    db = get_db()
    db.execute("UPDATE users SET password=? WHERE id=?", (new_pass, uid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>/storage', methods=['PUT'])
@owner_required
def update_user_storage(uid):
    d        = request.get_json() or {}
    limit_mb = int(d.get('storage_limit_mb', 500))
    db = get_db()
    db.execute("UPDATE users SET storage_limit_mb=? WHERE id=?", (limit_mb, uid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/me/storage')
@login_required
def my_storage():
    db   = get_db()
    user = db.execute(
        "SELECT storage_limit_mb, storage_used_mb FROM users WHERE id=?", (current_user_id(),)
    ).fetchone()
    if not user:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'storage_limit_mb': user['storage_limit_mb'],
        'storage_used_mb':  round(user['storage_used_mb'], 2),
        'storage_pct':      round(user['storage_used_mb'] / user['storage_limit_mb'] * 100, 1) if user['storage_limit_mb'] else 0
    })

def _update_storage(user_id, delta_bytes, db):
    """Add or subtract bytes from user's storage_used_mb."""
    delta_mb = delta_bytes / (1024 * 1024)
    db.execute(
        "UPDATE users SET storage_used_mb = MAX(0, storage_used_mb + ?) WHERE id=?",
        (delta_mb, user_id)
    )

def _check_storage(user_id, file_size_bytes, db):
    """Return True if user has enough storage for this file."""
    user = db.execute(
        "SELECT storage_limit_mb, storage_used_mb FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not user:
        return False
    needed_mb  = file_size_bytes / (1024 * 1024)
    used_mb    = user['storage_used_mb']
    limit_mb   = user['storage_limit_mb']
    return (used_mb + needed_mb) <= limit_mb

# ─────────────────────────── FILES ───────────────────────────────────────────
ALLOWED_IMG = {'jpg','jpeg','png','gif','webp'}
ALLOWED_VID = {'mp4','mov','webm','avi'}

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'الملف كبير جداً — حاول ضغط الصور'}), 413

def save_dataurl(dataurl, allowed_exts, user_id=None):
    if not dataurl or not isinstance(dataurl, str):
        return None
    m = re.match(r'data:([^;]+);base64,(.+)', dataurl, re.DOTALL)
    if not m: return None
    mime, b64 = m.group(1), m.group(2)
    ext = {
        'image/jpeg':'jpg','image/jpg':'jpg','image/png':'png',
        'image/gif':'gif','image/webp':'webp',
        'image/heic':'jpg','image/heif':'jpg',
        'video/mp4':'mp4','video/quicktime':'mov',
        'video/webm':'webm','video/avi':'avi'
    }.get(mime.lower(), 'bin')
    if ext not in allowed_exts: return None

    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        raw = base64.b64decode(b64)
        file_size = len(raw)

        # Check storage limit if user_id provided
        if user_id:
            db = get_db()
            if not _check_storage(user_id, file_size, db):
                return '__STORAGE_LIMIT__'

        with open(fpath, 'wb') as f:
            f.write(raw)

        if ext in ('jpg','jpeg','png','webp'):
            optimize_image(fpath)

        # Update storage usage
        if user_id:
            actual_size = os.path.getsize(fpath)
            db = get_db()
            _update_storage(user_id, actual_size, db)
            db.commit()

        return f"/uploads/{fname}"
    except Exception as e:
        print(f"save_dataurl error: {e}")
        return None

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️ Pillow not installed — images won't be optimized")

def optimize_image(filepath, max_dim=1920, quality=82):
    if not HAS_PIL: return False
    try:
        ext = filepath.rsplit('.', 1)[-1].lower()
        if ext in ('gif', 'svg'): return False
        img = Image.open(filepath)
        img = ImageOps.exif_transpose(img)
        if ext in ('jpg','jpeg') and img.mode in ('RGBA','P'):
            bg = Image.new('RGB', img.size, (255,255,255))
            bg.paste(img, mask=img.split()[-1] if img.mode=='RGBA' else None)
            img = bg
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        save_kwargs = {'optimize': True}
        if ext in ('jpg','jpeg'):
            save_kwargs.update({'quality': quality, 'progressive': True})
        elif ext == 'webp':
            save_kwargs.update({'quality': quality, 'method': 6})
        elif ext == 'png':
            save_kwargs['compress_level'] = 7
        img.save(filepath, **save_kwargs)
        return True
    except Exception as e:
        print(f"optimize_image error for {filepath}: {e}")
        return False

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'لا يوجد ملف'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'اسم الملف فارغ'}), 400
    kind    = request.form.get('kind', 'image')
    allowed = ALLOWED_VID if kind == 'video' else ALLOWED_IMG
    ext     = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext in ('heic','heif'): ext = 'jpg'
    if ext not in allowed:
        return jsonify({'error': f'نوع غير مسموح: {ext}'}), 400

    # Check storage
    uid = current_user_id()
    db  = get_db()
    f.seek(0, 2); file_size = f.tell(); f.seek(0)
    if not _check_storage(uid, file_size, db):
        return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة — تواصل مع الدعم لزيادة مساحتك'}), 400

    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        f.save(fpath)
        if kind != 'video':
            optimize_image(fpath)
        actual_size = os.path.getsize(fpath)
        _update_storage(uid, actual_size, db)
        db.commit()
        return jsonify({'url': f"/uploads/{fname}"})
    except Exception as e:
        return jsonify({'error': f'فشل الحفظ: {str(e)}'}), 500

def delete_file(url, user_id=None):
    if url and url.startswith('/uploads/'):
        p = os.path.join(UPLOAD_DIR, os.path.basename(url))
        if os.path.exists(p):
            file_size = os.path.getsize(p)
            os.remove(p)
            if user_id:
                db = get_db()
                _update_storage(user_id, -file_size, db)
                db.commit()

# ─────────────────────────── PROJECTS ─────────────────────────────────────────
def _migrate_modules_base64(mods, pid, db, user_id):
    changed = False
    out = []
    for mod in mods or []:
        if not isinstance(mod, dict):
            out.append(mod); continue
        mod = dict(mod)
        mtype = mod.get('type')
        if mtype == 'image':
            src = mod.get('src','')
            if isinstance(src, str) and src.startswith('data:'):
                url = save_dataurl(src, ALLOWED_IMG, user_id)
                if url and url != '__STORAGE_LIMIT__':
                    mod['src'] = url; changed = True
        elif mtype in ('photo-grid','grid'):
            new_items = []
            for item in mod.get('items',[]) or []:
                if isinstance(item, dict):
                    item = dict(item)
                    s = item.get('src','')
                    if isinstance(s, str) and s.startswith('data:'):
                        url = save_dataurl(s, ALLOWED_IMG, user_id)
                        if url and url != '__STORAGE_LIMIT__':
                            item['src'] = url; changed = True
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
    imgs = db.execute(
        'SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order', (row['id'],)
    ).fetchall()
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    mods = _migrate_modules_base64(mods, row['id'], db, row['user_id'])
    return {
        'id': row['id'], 'title': row['title'], 'category': row['category'],
        'description': row['description'] or '', 'mediaType': row['media_type'],
        'coverImage': row['cover_url'], 'videoUrl': row['video_url'],
        'images': [r['url'] for r in imgs], 'date': row['created_at'][:10],
        'projectType': row['project_type'] or 'grid',
        'modules': mods
    }

@app.route('/api/projects/<int:pid>/modules', methods=['GET'])
@login_required
def get_modules(pid):
    uid = current_user_id()
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not row: abort(404)
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    return jsonify({'modules': mods, 'project': project_to_dict(row, db)})

@app.route('/api/projects/<int:pid>/modules', methods=['PUT'])
@login_required
def save_modules(pid):
    uid = current_user_id()
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not row: abort(404)
    d            = request.get_json()
    modules      = d.get('modules', [])
    project_type = d.get('projectType', row['project_type'] or 'grid')

    processed = []
    for mod in modules:
        mod   = dict(mod)
        mtype = mod.get('type')
        if mtype == 'image' and mod.get('src','').startswith('data:'):
            url = save_dataurl(mod['src'], ALLOWED_IMG, uid)
            if url == '__STORAGE_LIMIT__':
                return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة'}), 400
            mod['src'] = url or mod['src']
        if mtype in ('photo-grid','grid'):
            new_items = []
            for item in mod.get('items',[]) or []:
                item = dict(item) if isinstance(item, dict) else {}
                src  = item.get('src','') if isinstance(item, dict) else ''
                if src and src.startswith('data:'):
                    url = save_dataurl(src, ALLOWED_IMG, uid)
                    if url == '__STORAGE_LIMIT__':
                        return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة'}), 400
                    item['src'] = url or src
                new_items.append(item)
            mod['items'] = new_items
        processed.append(mod)

    db.execute('UPDATE projects SET modules=?, project_type=? WHERE id=?',
               (json.dumps(processed), project_type, pid))

    if project_type == 'grid' and processed:
        img_modules = [m for m in processed if m.get('type') == 'image' and m.get('src')]
        if img_modules:
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
    uid = current_user_id()
    ids = request.get_json().get('ids', [])
    db  = get_db()
    for i, pid in enumerate(ids):
        db.execute('UPDATE projects SET sort_order=? WHERE id=? AND user_id=?', (len(ids)-i, pid, uid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/projects')
def get_projects():
    # Public: needs user_id from query param OR session
    uid = session.get('user_id')
    if not uid:
        # Public view: get user from subdomain or query param
        uid_param = request.args.get('user_id')
        if uid_param:
            uid = int(uid_param)
        else:
            # Default to owner for backwards compatibility
            db = get_db()
            owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
            uid = owner['id'] if owner else 1
    db   = get_db()
    rows = db.execute(
        'SELECT * FROM projects WHERE user_id=? ORDER BY sort_order DESC, id DESC', (uid,)
    ).fetchall()
    return jsonify([project_to_dict(r, db) for r in rows])

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    uid = current_user_id()
    d   = request.get_json()
    title = (d.get('title') or '').strip()
    if not title:
        return jsonify({'error':'العنوان مطلوب'}), 400

    cov = d.get('coverImage')
    if cov and cov.startswith('data:'):
        cover_url = save_dataurl(cov, ALLOWED_IMG, uid)
        if cover_url == '__STORAGE_LIMIT__':
            return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة'}), 400
    elif cov and cov.startswith('/uploads/'):
        cover_url = cov
    else:
        cover_url = None

    embed_url = d.get('embedUrl')
    if embed_url:
        video_url = embed_url
    else:
        vd = d.get('videoData')
        if vd and vd.startswith('data:'):
            video_url = save_dataurl(vd, ALLOWED_VID, uid)
            if video_url == '__STORAGE_LIMIT__':
                return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة'}), 400
        elif vd and vd.startswith('/uploads/'):
            video_url = vd
        else:
            video_url = None

    db  = get_db()
    cur = db.execute(
        'INSERT INTO projects(user_id,title,category,description,media_type,cover_url,video_url,project_type) VALUES(?,?,?,?,?,?,?,?)',
        (uid, title, d.get('category','Social Media'), d.get('description',''),
         d.get('mediaType','image'), cover_url, video_url, d.get('projectType','grid'))
    )
    pid = cur.lastrowid
    for i, img in enumerate(d.get('images',[])):
        if img.startswith('data:'):
            url = save_dataurl(img, ALLOWED_IMG, uid)
            if url == '__STORAGE_LIMIT__':
                break
        elif img.startswith('/uploads/'):
            url = img
        else:
            url = None
        if url and url != '__STORAGE_LIMIT__':
            db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,url,i))
    db.commit()
    return jsonify(project_to_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(), db)), 201

@app.route('/api/projects/<int:pid>', methods=['PUT'])
@login_required
def update_project(pid):
    uid = current_user_id()
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not row: abort(404)
    d = request.get_json()

    def resolve_file(field, old_url, allowed):
        v = d.get(field)
        if v is None:   return old_url
        if v == '':     delete_file(old_url, uid); return None
        if v.startswith('data:'):
            delete_file(old_url, uid)
            url = save_dataurl(v, allowed, uid)
            return None if url == '__STORAGE_LIMIT__' else url
        if v.startswith('/uploads/'):
            if v != old_url: delete_file(old_url, uid)
            return v
        return old_url

    cover_url = resolve_file('coverImage', row['cover_url'], ALLOWED_IMG)
    if d.get('embedUrl'):
        if row['video_url'] and not row['video_url'].startswith('http'):
            delete_file(row['video_url'], uid)
        video_url = d['embedUrl']
    else:
        video_url = resolve_file('videoData', row['video_url'], ALLOWED_VID)

    db.execute(
        'UPDATE projects SET title=?,category=?,description=?,media_type=?,cover_url=?,video_url=? WHERE id=?',
        ((d.get('title') or row['title']).strip(), d.get('category',row['category']),
         d.get('description',row['description']), d.get('mediaType',row['media_type']),
         cover_url, video_url, pid)
    )
    if 'projectType' in d:
        db.execute('UPDATE projects SET project_type=? WHERE id=?', (d['projectType'], pid))

    keep     = d.get('keepImages') or []
    new_imgs = d.get('images') or []
    if 'keepImages' in d or 'images' in d:
        old = db.execute('SELECT url FROM project_images WHERE project_id=?', (pid,)).fetchall()
        kept = set(keep)
        for o in old:
            if o['url'] not in kept: delete_file(o['url'], uid)
        db.execute('DELETE FROM project_images WHERE project_id=?', (pid,))
        for i, url in enumerate(keep):
            db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,url,i))
        for i, img in enumerate(new_imgs):
            if not img: continue
            if img.startswith('data:'):
                url = save_dataurl(img, ALLOWED_IMG, uid)
                if url == '__STORAGE_LIMIT__': break
            elif img.startswith('/uploads/'):
                url = img
            else:
                url = None
            if url and url != '__STORAGE_LIMIT__':
                db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',
                           (pid, url, len(keep)+i))

    ptype = d.get('projectType', row['project_type'] or 'grid')
    if ptype == 'grid' and d.get('mediaType','image') != 'video':
        imgs = db.execute(
            'SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order', (pid,)
        ).fetchall()
        mods = [{'type':'image','src':r['url']} for r in imgs if r['url']]
        db.execute('UPDATE projects SET modules=? WHERE id=?', (json.dumps(mods), pid))

    db.commit()
    return jsonify(project_to_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(), db))

@app.route('/api/projects/<int:pid>', methods=['DELETE'])
@login_required
def delete_project(pid):
    uid = current_user_id()
    db  = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, uid)).fetchone()
    if not row: abort(404)
    delete_file(row['cover_url'], uid)
    delete_file(row['video_url'], uid)
    for img in db.execute('SELECT url FROM project_images WHERE project_id=?', (pid,)).fetchall():
        delete_file(img['url'], uid)
    db.execute('DELETE FROM projects WHERE id=?', (pid,))
    db.commit()
    return jsonify({'ok': True})

# ─────────────────────────── SETTINGS ─────────────────────────────────────────
@app.route('/api/settings')
def get_settings():
    # Public: get user from session or query param
    uid = session.get('user_id')
    if not uid:
        uid_param = request.args.get('user_id')
        if uid_param:
            uid = int(uid_param)
        else:
            db    = get_db()
            owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
            uid   = owner['id'] if owner else 1

    db   = get_db()
    rows = db.execute('SELECT key,value FROM settings WHERE user_id=?', (uid,)).fetchall()
    out  = {}
    for r in rows:
        try:    out[r['key']] = json.loads(r['value'])
        except: out[r['key']] = r['value']
    return jsonify(out)

@app.route('/api/settings', methods=['PUT'])
@login_required
def update_settings():
    uid = current_user_id()
    d   = request.get_json()
    db  = get_db()

    for upload_key, store_key in [
        ('photo_upload','photo_url'),
        ('hero_cover_upload','hero_cover_url'),
        ('brand_logo_upload','brand_logo_url'),
        ('favicon_upload','favicon_url'),
    ]:
        img = d.pop(upload_key, None)
        if img and isinstance(img, str) and img.startswith('data:'):
            old = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (uid, store_key)).fetchone()
            if old and old['value']: delete_file(old['value'], uid)
            url = save_dataurl(img, ALLOWED_IMG, uid)
            if url == '__STORAGE_LIMIT__':
                return jsonify({'error': '⚠️ وصلت للحد الأقصى من المساحة'}), 400
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (uid, store_key, url or ''))
        elif img and isinstance(img, str) and img.startswith('/uploads/'):
            old = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (uid, store_key)).fetchone()
            if old and old['value'] and old['value'] != img:
                delete_file(old['value'], uid)
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (uid, store_key, img))
        elif img == '':
            old = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (uid, store_key)).fetchone()
            if old and old['value']: delete_file(old['value'], uid)
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (uid, store_key, ''))

    tool_img_uploads = {k:v for k,v in d.items() if k.startswith('tool_img_upload_')}
    for key in tool_img_uploads:
        d.pop(key)
    for key, img in tool_img_uploads.items():
        if img and img.startswith('data:'):
            url = save_dataurl(img, ALLOWED_IMG, uid)
            if url and url != '__STORAGE_LIMIT__':
                db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)',
                           (uid, key.replace('upload','url'), url))
        elif img == '':
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)',
                       (uid, key.replace('upload','url'), ''))

    for k, v in d.items():
        val = json.dumps(v) if isinstance(v, (dict,list)) else str(v)
        db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (uid, k, val))
    db.commit()
    return jsonify({'ok': True})

# ─────────────────────────── IMPORT UTILITIES ──────────────────────────────────
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

@app.route('/api/behance/fetch', methods=['POST'])
@login_required
def behance_fetch():
    url = (request.get_json() or {}).get('url','').strip()
    if 'behance.net' not in url:
        return jsonify({'error':'يجب أن يكون رابط Behance'}), 400
    try:
        body, _ = fetch_url(url)
        title = ''
        t = re.search(r'<meta property="og:title"\s+content="([^"]+)"', body)
        if t: title = html_mod.unescape(t.group(1))
        if not title:
            t2 = re.search(r'<title>([^<]+)</title>', body)
            if t2: title = html_mod.unescape(t2.group(1).split('::')[0].strip())
        desc = ''
        d = re.search(r'<meta property="og:description"\s+content="([^"]+)"', body)
        if d: desc = html_mod.unescape(d.group(1))
        cover_match = re.search(r'<meta property="og:image"\s+content="([^"]+)"', body)
        cover = html_mod.unescape(cover_match.group(1)) if cover_match else ''
        img_urls = []
        for m in re.finditer(r'"url"\s*:\s*"(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"]+)"', body):
            u = m.group(1)
            if 'fs/' in u or 'max_1200/' in u or 'max_3840/' in u:
                if u not in img_urls: img_urls.append(u)
        if not img_urls:
            for m in re.finditer(r'(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"\s]+\.(?:jpg|png|jpeg|webp))', body):
                u = m.group(1)
                if u not in img_urls: img_urls.append(u)
        cover_b64 = ''
        if cover:
            try:
                r2 = proxy_one(cover)
                if r2: cover_b64 = r2
            except: pass
        return jsonify({
            'title': title, 'description': desc,
            'cover': cover, 'cover_b64': cover_b64,
            'images': img_urls[:20],
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
    urls    = (request.get_json() or {}).get('urls', [])[:12]
    results = []
    for url in urls:
        try:    results.append(proxy_one(url))
        except: results.append(None)
    return jsonify({'images': results})

@app.route('/api/auth/credentials', methods=['PUT'])
@login_required
def change_credentials():
    uid      = current_user_id()
    d        = request.get_json() or {}
    new_user = d.get('username','').strip()
    new_pass = d.get('password','').strip()
    old_pass = d.get('old_password','').strip()

    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user or old_pass != user['password']:
        return jsonify({'error':'كلمة المرور الحالية غير صحيحة'}), 403
    if not new_user or not new_pass:
        return jsonify({'error':'أدخل اسم المستخدم وكلمة المرور'}), 400
    if len(new_pass) < 6:
        return jsonify({'error':'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

    db.execute("UPDATE users SET username=?, password=? WHERE id=?", (new_user, new_pass, uid))
    db.commit()
    session['username'] = new_user
    return jsonify({'ok': True})

# ─────────────────────────── STATIC ───────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    response = send_from_directory(UPLOAD_DIR, filename)
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response

@app.route('/admin')
@app.route('/admin.html')
def admin_page():
    return send_from_directory(app.static_folder, 'admin.html')

# ─────────────────────────── CONTACT FORM ─────────────────────────────────────
_contact_rate = {}

@app.route('/api/contact', methods=['POST'])
def contact_send():
    ip  = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    now = time.time()
    _contact_rate.setdefault(ip, [])
    _contact_rate[ip] = [t for t in _contact_rate[ip] if now - t < 3600]
    if len(_contact_rate[ip]) >= 3:
        return jsonify({'error': 'تم تجاوز الحد المسموح. حاول بعد ساعة.'}), 429

    data    = request.get_json() or {}
    name    = (data.get('name') or '').strip()[:100]
    email   = (data.get('email') or '').strip()[:200]
    subject = (data.get('subject') or '').strip()[:200]
    message = (data.get('message') or '').strip()[:5000]

    if not name or not email or not message:
        return jsonify({'error': 'الاسم والإيميل والرسالة مطلوبة'}), 400
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'error': 'البريد الإلكتروني غير صحيح'}), 400

    api_key  = os.environ.get('RESEND_API_KEY', '')
    to_email = os.environ.get('CONTACT_EMAIL', '')
    if not api_key or not to_email:
        return jsonify({'error': 'خدمة الإيميل غير مهيأة'}), 500

    def esc(s):
        return html_mod.escape(s).replace('\n', '<br>')

    subject_line = subject if subject else f'رسالة جديدة من {name}'
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5;">
      <div style="background:#fff;padding:24px;border-radius:8px;border-top:4px solid #ff6b35;">
        <h2 style="color:#ff6b35;margin-top:0;">📬 رسالة جديدة من موقعك</h2>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr><td style="padding:8px;background:#fafafa;font-weight:bold;width:120px;">الاسم:</td><td style="padding:8px;">{esc(name)}</td></tr>
          <tr><td style="padding:8px;background:#fafafa;font-weight:bold;">الإيميل:</td><td style="padding:8px;"><a href="mailto:{esc(email)}">{esc(email)}</a></td></tr>
          {f'<tr><td style="padding:8px;background:#fafafa;font-weight:bold;">الموضوع:</td><td style="padding:8px;">{esc(subject)}</td></tr>' if subject else ''}
        </table>
        <div style="margin-top:20px;padding:16px;background:#fafafa;border-right:3px solid #ff6b35;">
          <strong style="color:#666;">الرسالة:</strong><br><br>{esc(message)}
        </div>
      </div>
    </div>
    """
    payload = {
        'from': 'Portfolio Contact <onboarding@resend.dev>',
        'to': [to_email], 'reply_to': email,
        'subject': subject_line, 'html': html_body,
    }
    try:
        req = urllib.request.Request(
            'https://api.resend.com/emails',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            }, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode('utf-8'))
            if result.get('id'):
                _contact_rate[ip].append(now)
                return jsonify({'ok': True})
            return jsonify({'error': 'فشل الإرسال'}), 500
    except urllib.error.HTTPError as e:
        print(f"Resend error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return jsonify({'error': 'فشل إرسال الإيميل'}), 500
    except Exception as e:
        print(f"Contact form error: {e}")
        return jsonify({'error': 'حدث خطأ غير متوقع'}), 500

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    full = os.path.join(app.static_folder, path)
    if path and os.path.exists(full):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀  http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV')=='development')

# ─────────────────────────── DOMAIN ROUTING ───────────────────────────────────
@app.route('/u/<username>')
@app.route('/u/<username>/')
def user_portfolio_page(username):
    """Serve portfolio page for /u/<username> URLs."""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/resolve-user')
def resolve_user():
    """Resolve which user_id to show based on hostname or username."""
    username = request.args.get('username', '').strip()
    host     = request.args.get('host', '').strip().lower().split(':')[0]
    db       = get_db()

    if username:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if user:
            return jsonify({'user_id': user['id']})
        return jsonify({'error': 'not found'}), 404

    if host:
        domain = db.execute("SELECT user_id FROM domains WHERE domain=?", (host,)).fetchone()
        if domain:
            return jsonify({'user_id': domain['user_id']})

    # Default: owner
    owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
    return jsonify({'user_id': owner['id'] if owner else 1})

@app.route('/api/users/<int:uid>/domain', methods=['GET'])
@owner_required
def get_user_domain(uid):
    db     = get_db()
    domain = db.execute("SELECT domain FROM domains WHERE user_id=?", (uid,)).fetchone()
    return jsonify({'domain': domain['domain'] if domain else ''})

@app.route('/api/users/<int:uid>/domain', methods=['PUT'])
@owner_required
def set_user_domain(uid):
    d      = request.get_json() or {}
    domain = (d.get('domain') or '').strip().lower()
    # Remove protocol if user pasted full URL
    domain = re.sub(r'^https?://', '', domain).rstrip('/')
    db     = get_db()
    if domain:
        db.execute("INSERT OR REPLACE INTO domains(user_id,domain) VALUES(?,?)", (uid, domain))
    else:
        db.execute("DELETE FROM domains WHERE user_id=?", (uid,))
    db.commit()
    return jsonify({'ok': True})
