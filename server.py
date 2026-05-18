import os, sqlite3, json, secrets, uuid, re, base64, time, shutil, threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from flask import Flask, request, jsonify, session, send_from_directory, abort, redirect, send_file, Response
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')

# ── SECURITY ──
_env_secret = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.secret_key = _env_secret
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('RENDER','') == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
CORS(app, supports_credentials=True)

DB_PATH    = '/var/data/portfolio.db'
UPLOAD_DIR = '/var/data/uploads'
BACKUP_DIR = '/var/data/backups'
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

OWNER_USER = os.environ.get('ADMIN_USER', 'admin')
OWNER_PASS = os.environ.get('ADMIN_PASS', 'admin123')
OWNER_SECRET = os.environ.get('OWNER_SECRET', 'owner_secret_key')  # كلمة مرور صفحة /owner

# ── RATE LIMITING ──
_login_attempts = defaultdict(lambda: deque(maxlen=20))
LOGIN_MAX = 5
LOGIN_WIN = 15 * 60
LOGIN_LOCK = 30 * 60

def check_rate_limit(ip):
    now = time.time()
    q = _login_attempts[ip]
    while q and now - q[0] > LOGIN_WIN: q.popleft()
    if len(q) >= LOGIN_MAX:
        wait = int(LOGIN_LOCK - (now - q[0]))
        if wait > 0: return False, wait
        q.clear()
    return True, 0

def record_fail(ip): _login_attempts[ip].append(time.time())
def reset_attempts(ip): _login_attempts[ip].clear()

# ── AUTO BACKUP ──
def auto_backup():
    def _loop():
        while True:
            try:
                if os.path.exists(DB_PATH):
                    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dst = os.path.join(BACKUP_DIR, f'portfolio_{stamp}.db')
                    shutil.copy2(DB_PATH, dst)
                    bks = sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith('.db'))
                    while len(bks) > 7:
                        try: os.remove(os.path.join(BACKUP_DIR, bks.pop(0)))
                        except: pass
                    # Cleanup old visits (keep 1 year)
                    try:
                        c = sqlite3.connect(DB_PATH)
                        c.execute("DELETE FROM visits WHERE visited_at < datetime('now','-365 days')")
                        c.commit()
                        c.close()
                    except: pass
            except Exception as e:
                print(f'Backup error: {e}')
            time.sleep(6 * 3600)
    threading.Thread(target=_loop, daemon=True).start()

auto_backup()

# ── DB DEFAULTS ──
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys = ON')
    return c

DEFAULT_COLORS   = json.dumps({"accent":"#F97316","bg":"#0A0A0A","bg2":"#111111","text":"#FFFFFF","subtext":"#999999"})
DEFAULT_SECTIONS = json.dumps([
    {"id":"hero",         "label_ar":"الرئيسية",   "label_en":"Hero",          "visible":True,"order":0},
    {"id":"about",        "label_ar":"عن النفس",    "label_en":"About",         "visible":True,"order":1},
    {"id":"expertise",    "label_ar":"الخدمات",     "label_en":"Key Expertise", "visible":True,"order":2},
    {"id":"education",    "label_ar":"التعليم",      "label_en":"Education",     "visible":True,"order":3},
    {"id":"skills",       "label_ar":"المهارات",     "label_en":"Skills",        "visible":True,"order":4},
    {"id":"tools",        "label_ar":"الأدوات",      "label_en":"Tools",         "visible":True,"order":5},
    {"id":"experience",   "label_ar":"الخبرات",      "label_en":"Experience",    "visible":True,"order":6},
    {"id":"projects",     "label_ar":"المشاريع",     "label_en":"Projects",      "visible":True,"order":7},
    {"id":"logos",        "label_ar":"العملاء",      "label_en":"Clients",       "visible":True,"order":8},
    {"id":"testimonials",  "label_ar":"آراء العملاء","label_en":"Testimonials",  "visible":True,"order":9},
    {"id":"achievements",  "label_ar":"الإنجازات",   "label_en":"Achievements",  "visible":True,"order":10},
    {"id":"contact",       "label_ar":"تواصل معي",   "label_en":"Contact",       "visible":True,"order":11},
])
DEFAULT_CONTENT = json.dumps({
    "hero":{"name_en":"Your Name","name_ar":"اسمك","title_en":"Graphic Designer","title_ar":"مصمم جرافيك","btn1_en":"View Work","btn1_ar":"أعمالي","btn2_en":"Get In Touch","btn2_ar":"تواصل معي"},
    "about":{"text_en":"I'm a passionate designer.","text_ar":"أنا مصمم متحمس.","tags_en":"Brand Identity,Social Media","tags_ar":"هوية بصرية,سوشيال ميديا"},
    "education":{"items":"[]"},"skills":{"items_en":"","items_ar":""},"tools":{"items":"[]"},
    "experience":{"items":"[]"},
    "expertise":{"title_en":"Key Expertise","title_ar":"خدماتي","items":"[]"},
    "projects":{"title_en":"Selected Work","title_ar":"أعمال مختارة","subtitle_en":"A collection of my work","subtitle_ar":"مجموعة من أعمالي"},
    "contact":{"title_en":"Let's Work Together","title_ar":"لنعمل معاً","subtitle_en":"Have a project in mind?","subtitle_ar":"لديك مشروع؟","email":"","phone":""},
})
DEFAULT_NAVBAR = json.dumps([
    {"id":"about","label_ar":"عن النفس","label_en":"About","visible":True},
    {"id":"expertise","label_ar":"الخدمات","label_en":"Services","visible":True},
    {"id":"experience","label_ar":"الخبرات","label_en":"Experience","visible":True},
    {"id":"projects","label_ar":"المشاريع","label_en":"Projects","visible":True},
    {"id":"contact","label_ar":"تواصل","label_en":"Contact","visible":True},
])
DEFAULT_IMG_CATS = json.dumps(['Social Media','Brand Identity','Logo Design','Print Design','Packaging','Posters','UI/UX'])
DEFAULT_VID_CATS = json.dumps(['Reels','Motion Graphics','Video Editing','AI Videos','Promo Ads','Tutorials'])

def default_settings(user_id, db):
    for k, v in [
        ('whatsapp',''),('behance',''),('instagram',''),('linkedin',''),('facebook',''),('vimeo',''),
        ('social_visible', json.dumps(['whatsapp','behance','instagram','linkedin','vimeo'])),
        ('photo_url',''),('hero_cover_url',''),
        ('video_cols_mobile','2'),('video_cols_tablet','3'),('video_cols_desktop','4'),
        ('image_cols_mobile','2'),('image_cols_tablet','3'),('image_cols_desktop','4'),
        ('vimeo_token',''),
        ('hero_cover_size','cover'),('hero_cover_pos_x','50'),('hero_cover_pos_y','50'),
        ('hero_cover_overlay','55'),('hero_height','85'),
        ('brand_logo_url',''),('favicon_url',''),
        ('image_categories', DEFAULT_IMG_CATS),
        ('video_categories', DEFAULT_VID_CATS),
        ('navbar_links', DEFAULT_NAVBAR),
        ('colors', DEFAULT_COLORS),
        ('sections', DEFAULT_SECTIONS),
        ('content', DEFAULT_CONTENT),
        # Design system defaults
        ('style_hero', 'centered'),
        ('style_about', 'classic'),
        ('style_font', 'default'),
        ('style_direction', 'auto'),
        ('style_bg_preset', 'dark'),
        ('style_bg_type', 'solid'),
        ('style_bg_color1', '#0a0a0a'),
        ('style_bg_color2', '#1a1a1a'),
        ('style_cursor', 'default'),
        ('style_anim', 'fade-up'),
        # Project section tabs (Designs / Reels / Videos): visibility + label + icon
        ('proj_tabs', json.dumps({
            'designs': {'visible': True, 'label_ar': 'التصاميم',  'label_en': 'Designs', 'icon': 'fa-solid fa-image'},
            'reels':   {'visible': True, 'label_ar': 'الريلز',    'label_en': 'Reels',   'icon': 'fa-solid fa-film'},
            'videos':  {'visible': True, 'label_ar': 'الفيديوهات','label_en': 'Videos',  'icon': 'fa-solid fa-video'},
        })),
        ('freegrid_cols_mobile','1'), ('freegrid_cols_desktop','2'),
    ]:
        db.execute('INSERT OR IGNORE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,k,v))
    db.commit()

# ── INIT DB ──
def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                username         TEXT UNIQUE NOT NULL,
                password         TEXT NOT NULL,
                storage_limit_mb INTEGER DEFAULT 500,
                storage_used_mb  REAL DEFAULT 0,
                is_owner         INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            );
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
                modules      TEXT DEFAULT '[]',
                aspect_ratio TEXT DEFAULT '9:16',
                video_kind   TEXT DEFAULT 'reel'
            );
            CREATE TABLE IF NOT EXISTS project_images (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                url        TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS domains (
                user_id    INTEGER UNIQUE NOT NULL,
                domain     TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS visits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                visited_at TEXT DEFAULT (datetime('now')),
                visitor_id TEXT,
                page       TEXT,
                project_id INTEGER,
                country    TEXT,
                device     TEXT,
                referrer   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_visits_user_date ON visits(user_id, visited_at);
            CREATE INDEX IF NOT EXISTS idx_visits_visitor ON visits(visitor_id, page);

            CREATE TABLE IF NOT EXISTS client_logos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT,
                logo_url    TEXT NOT NULL,
                website_url TEXT DEFAULT '',
                sort_order  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_logos_user ON client_logos(user_id, sort_order);

            CREATE TABLE IF NOT EXISTS testimonials (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                name         TEXT NOT NULL,
                role         TEXT DEFAULT '',
                company      TEXT DEFAULT '',
                content      TEXT NOT NULL,
                avatar_url   TEXT DEFAULT '',
                rating       INTEGER DEFAULT 5,
                source       TEXT DEFAULT 'admin',
                approved     INTEGER DEFAULT 1,
                sort_order   INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_test_user ON testimonials(user_id, approved, sort_order);

            CREATE TABLE IF NOT EXISTS achievements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                icon_url   TEXT DEFAULT '',
                title      TEXT DEFAULT '',
                value      TEXT DEFAULT '0',
                sort_order INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_ach_user ON achievements(user_id, sort_order);
        ''')

        # settings table with user_id
        s_cols = [r[1] for r in db.execute("PRAGMA table_info(settings)").fetchall()]
        if not s_cols:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (
                    user_id INTEGER NOT NULL,
                    key     TEXT NOT NULL,
                    value   TEXT,
                    PRIMARY KEY (user_id, key)
                );
            ''')
        elif 'user_id' not in s_cols:
            db.executescript('''
                CREATE TABLE settings_new (user_id INTEGER NOT NULL DEFAULT 1, key TEXT NOT NULL, value TEXT, PRIMARY KEY(user_id,key));
                INSERT OR IGNORE INTO settings_new(user_id,key,value) SELECT 1,key,value FROM settings;
                DROP TABLE settings;
                ALTER TABLE settings_new RENAME TO settings;
            ''')
        db.commit()

        # migrations for achievements
        ach_cols = [r[1] for r in db.execute("PRAGMA table_info(achievements)").fetchall()]
        if 'title_en' not in ach_cols:
            try: db.execute("ALTER TABLE achievements ADD COLUMN title_en TEXT DEFAULT ''"); db.commit()
            except: pass

        # migrations for projects
        p_cols = [r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()]
        for col, defval in [('user_id','1'),('project_type',"'grid'"),('modules',"'[]'"),
                            ('aspect_ratio',"'9:16'"),('video_kind',"'reel'")]:
            if col not in p_cols:
                try: db.execute(f'ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {defval}'); db.commit()
                except: pass

        # Owner account
        owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        if not owner:
            existing = db.execute("SELECT id FROM users WHERE username=?", (OWNER_USER,)).fetchone()
            if existing:
                db.execute("UPDATE users SET is_owner=1, storage_limit_mb=10240 WHERE id=?", (existing['id'],))
            else:
                db.execute("INSERT INTO users(username,password,storage_limit_mb,is_owner) VALUES(?,?,?,1)", (OWNER_USER, OWNER_PASS, 10240))
            db.commit()

        # Always sync owner credentials from env
        db.execute("UPDATE users SET username=?, password=?, is_owner=1 WHERE is_owner=1", (OWNER_USER, OWNER_PASS))
        db.commit()

        owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        owner_id = owner['id'] if owner else 1
        # Apply default settings to ALL users so new keys (proj_tabs, freegrid, etc.) propagate
        for u in db.execute("SELECT id FROM users").fetchall():
            default_settings(u['id'], db)

init_db()

# ── AUTH DECORATORS ──
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('logged_in'): return jsonify({'error':'Unauthorized'}), 401
        return f(*a, **kw)
    return d

def owner_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('logged_in'): return jsonify({'error':'Unauthorized'}), 401
        if not session.get('is_owner'):  return jsonify({'error':'ليس لديك صلاحية'}), 403
        return f(*a, **kw)
    return d

def uid(): return session.get('user_id', 1)

# ── LOGIN/LOGOUT ──
@app.route('/api/auth/login', methods=['POST'])
def login():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'x').split(',')[0].strip()
    ok, wait = check_rate_limit(ip)
    if not ok: return jsonify({'error': f'حاول بعد {wait//60+1} دقيقة'}), 429
    d = request.get_json() or {}
    user = get_db().execute("SELECT * FROM users WHERE username=? AND password=?", (d.get('username','').strip(), d.get('password','').strip())).fetchone()
    if user:
        session.update({'logged_in':True,'user_id':user['id'],'is_owner':bool(user['is_owner']),'username':user['username']})
        session.permanent = True
        reset_attempts(ip)
        return jsonify({'ok':True,'is_owner':bool(user['is_owner']),'username':user['username']})
    record_fail(ip)
    rem = LOGIN_MAX - len(_login_attempts[ip])
    msg = 'بيانات غير صحيحة' + (f' — متبقي {rem} محاولة' if 0 < rem <= 2 else '')
    return jsonify({'error': msg}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/auth/check')
def auth_check():
    return jsonify({'logged_in':bool(session.get('logged_in')),'is_owner':bool(session.get('is_owner')),'username':session.get('username',''),'user_id':session.get('user_id')})

# ── OWNER PAGE AUTH (separate from client auth) ──
@app.route('/api/owner/login', methods=['POST'])
def owner_login():
    d = request.get_json() or {}
    secret = d.get('secret','').strip()
    if secret != OWNER_SECRET:
        return jsonify({'error': 'كلمة المرور غير صحيحة'}), 401
    session['owner_panel'] = True
    return jsonify({'ok': True})

@app.route('/api/owner/logout', methods=['POST'])
def owner_logout():
    session.pop('owner_panel', None)
    return jsonify({'ok': True})

@app.route('/api/owner/check')
def owner_check():
    return jsonify({'ok': bool(session.get('owner_panel'))})

def owner_panel_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get('owner_panel'): return jsonify({'error':'Unauthorized'}), 401
        return f(*a, **kw)
    return d

# ── USERS MANAGEMENT (owner panel only) ──
@app.route('/api/owner/users', methods=['GET'])
@owner_panel_required
def list_users():
    users = get_db().execute("SELECT id,username,storage_limit_mb,storage_used_mb,is_owner,created_at FROM users ORDER BY id").fetchall()
    return jsonify([dict(u) for u in users])

def get_disk_total_mb():
    """Get real disk capacity from Render disk mount, with safety buffer."""
    try:
        total, _used, _free = shutil.disk_usage('/var/data')
        # 100 MB safety buffer for system files (DB, backups, etc.)
        return max(0, round(total / (1024 * 1024)) - 100)
    except Exception:
        return 0

def get_allocated_mb(db, exclude_user_id=None):
    """Sum of storage_limit_mb for ALL users (including owner)."""
    if exclude_user_id is not None:
        row = db.execute("SELECT COALESCE(SUM(storage_limit_mb),0) FROM users WHERE id != ?", (exclude_user_id,)).fetchone()
    else:
        row = db.execute("SELECT COALESCE(SUM(storage_limit_mb),0) FROM users").fetchone()
    return row[0] or 0

@app.route('/api/owner/users', methods=['POST'])
@owner_panel_required
def create_user():
    d = request.get_json() or {}
    username = (d.get('username') or '').strip()
    password = (d.get('password') or '').strip()
    limit_mb = int(d.get('storage_limit_mb', 500))
    if not username or not password: return jsonify({'error':'اسم المستخدم وكلمة المرور مطلوبان'}), 400
    if len(password) < 6: return jsonify({'error':'كلمة المرور 6 أحرف على الأقل'}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({'error':'اسم المستخدم موجود بالفعل'}), 400
    # ── Smart capacity check ──
    disk_total = get_disk_total_mb()
    allocated  = get_allocated_mb(db)
    available  = disk_total - allocated
    if disk_total > 0 and limit_mb > available:
        def fmt(mb): return f"{round(mb/1024,1)} GB" if mb >= 1024 else f"{mb} MB"
        return jsonify({
            'error': f'⚠️ لا تكفي المساحة. الديسك {fmt(disk_total)} | المخصص للعملاء {fmt(allocated)} | المتاح فقط {fmt(max(0,available))}'
        }), 400
    cur = db.execute("INSERT INTO users(username,password,storage_limit_mb,is_owner) VALUES(?,?,?,0)", (username,password,limit_mb))
    db.commit()
    new_id = cur.lastrowid
    default_settings(new_id, db)
    return jsonify({'ok':True,'id':new_id,'username':username}), 201

@app.route('/api/owner/users/<int:uid_>', methods=['DELETE'])
@owner_panel_required
def delete_user(uid_):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid_,)).fetchone()
    if not user: return jsonify({'error':'المستخدم غير موجود'}), 404
    if user['is_owner']: return jsonify({'error':'لا يمكن حذف المالك'}), 400
    for p in db.execute("SELECT cover_url,video_url FROM projects WHERE user_id=?", (uid_,)).fetchall():
        delete_file(p['cover_url']); delete_file(p['video_url'])
    for img in db.execute("SELECT pi.url FROM project_images pi JOIN projects p ON pi.project_id=p.id WHERE p.user_id=?", (uid_,)).fetchall():
        delete_file(img['url'])
    db.execute("DELETE FROM projects WHERE user_id=?", (uid_,))
    db.execute("DELETE FROM settings WHERE user_id=?", (uid_,))
    db.execute("DELETE FROM domains WHERE user_id=?", (uid_,))
    db.execute("DELETE FROM users WHERE id=?", (uid_,))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/owner/users/<int:uid_>/password', methods=['PUT'])
@owner_panel_required
def change_user_password(uid_):
    pw = (request.get_json() or {}).get('password','').strip()
    if len(pw) < 6: return jsonify({'error':'كلمة المرور 6 أحرف على الأقل'}), 400
    db = get_db()
    db.execute("UPDATE users SET password=? WHERE id=?", (pw, uid_))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/owner/users/<int:uid_>/storage', methods=['PUT'])
@owner_panel_required
def update_user_storage(uid_):
    limit = int((request.get_json() or {}).get('storage_limit_mb', 500))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid_,)).fetchone()
    if not user: return jsonify({'error':'المستخدم غير موجود'}), 404
    # Don't allow shrinking below currently used storage
    if limit < user['storage_used_mb']:
        return jsonify({'error': f'⚠️ لا يمكن تقليل المساحة أقل من المستخدم فعلاً ({round(user["storage_used_mb"],1)} MB)'}), 400
    # ── Smart capacity check (excluding this user) ──
    disk_total = get_disk_total_mb()
    allocated_others = get_allocated_mb(db, exclude_user_id=uid_)
    available = disk_total - allocated_others
    if disk_total > 0 and limit > available:
        def fmt(mb): return f"{round(mb/1024,1)} GB" if mb >= 1024 else f"{mb} MB"
        return jsonify({
            'error': f'⚠️ لا تكفي المساحة. الديسك {fmt(disk_total)} | المخصص لباقي العملاء {fmt(allocated_others)} | المتاح لهذا العميل {fmt(max(0,available))}'
        }), 400
    db.execute("UPDATE users SET storage_limit_mb=? WHERE id=?", (limit, uid_))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/owner/users/<int:uid_>/domain', methods=['GET'])
@owner_panel_required
def get_user_domain(uid_):
    d = get_db().execute("SELECT domain FROM domains WHERE user_id=?", (uid_,)).fetchone()
    return jsonify({'domain': d['domain'] if d else ''})

@app.route('/api/owner/users/<int:uid_>/domain', methods=['PUT'])
@owner_panel_required
def set_user_domain(uid_):
    domain = re.sub(r'^https?://', '', (request.get_json() or {}).get('domain','').strip().lower()).rstrip('/')
    db = get_db()
    if domain: db.execute("INSERT OR REPLACE INTO domains(user_id,domain) VALUES(?,?)", (uid_, domain))
    else:       db.execute("DELETE FROM domains WHERE user_id=?", (uid_,))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/owner/stats')
@owner_panel_required
def owner_stats():
    db = get_db()
    total_users    = db.execute("SELECT COUNT(*) FROM users WHERE is_owner=0").fetchone()[0]
    new_this_month = db.execute(
        "SELECT COUNT(*) FROM users WHERE is_owner=0 AND created_at >= datetime('now', 'start of month')"
    ).fetchone()[0]
    # Real disk + allocation
    try:
        total, used, _free = shutil.disk_usage('/var/data')
        disk_total_mb = round(total / (1024 * 1024))
        disk_used_mb  = round(used  / (1024 * 1024), 1)
        disk_pct = round(used / total * 100, 1) if total else 0
    except Exception:
        disk_total_mb = disk_used_mb = disk_pct = 0
    safe_total = get_disk_total_mb()  # capacity minus 100MB buffer
    allocated  = get_allocated_mb(db)
    available  = max(0, safe_total - allocated)
    alloc_pct  = round(allocated / safe_total * 100, 1) if safe_total else 0
    return jsonify({
        'total_users': total_users,
        'new_this_month': new_this_month,
        'disk_used_mb': disk_used_mb,
        'disk_total_mb': disk_total_mb,
        'disk_pct': disk_pct,
        'allocated_mb': allocated,
        'available_mb': available,
        'alloc_pct': alloc_pct,
        'safe_total_mb': safe_total,
    })

# ── MY STORAGE (client) ──
@app.route('/api/me/storage')
@login_required
def my_storage():
    user = get_db().execute("SELECT storage_limit_mb, storage_used_mb FROM users WHERE id=?", (uid(),)).fetchone()
    if not user: return jsonify({'error':'not found'}), 404
    return jsonify({'storage_limit_mb':user['storage_limit_mb'],'storage_used_mb':round(user['storage_used_mb'],2),'storage_pct':round(user['storage_used_mb']/user['storage_limit_mb']*100,1) if user['storage_limit_mb'] else 0})

# ══════════════ ANALYTICS ══════════════

def detect_device(ua):
    ua = (ua or '').lower()
    if 'ipad' in ua or 'tablet' in ua: return 'tablet'
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua: return 'mobile'
    return 'desktop'

@app.route('/api/track', methods=['POST'])
def track_visit():
    """Public endpoint — records a visit. Skips owner viewing own portfolio."""
    d = request.get_json() or {}
    try: user_id = int(d.get('user_id', 0))
    except: user_id = 0
    if not user_id: return jsonify({'ok':False}), 400

    # Skip if viewer is the portfolio owner (logged in admin viewing own site)
    if session.get('logged_in') and session.get('user_id') == user_id:
        return jsonify({'ok':True, 'skipped':'self'})

    visitor_id = (d.get('visitor_id') or '')[:64]
    page       = (d.get('page') or 'home')[:50]
    referrer   = (d.get('referrer') or '')[:200]
    try: project_id = int(d.get('project_id')) if d.get('project_id') else None
    except: project_id = None

    device  = detect_device(request.headers.get('User-Agent', ''))
    # Country from Cloudflare header (if behind CF) or X-Country header
    country = (request.headers.get('CF-IPCountry') or request.headers.get('X-Country') or '')[:2].upper()
    if country in ('XX', 'T1'): country = ''

    db = get_db()
    # Throttle: same visitor + same page within 30 min = skip duplicate
    if visitor_id:
        recent = db.execute(
            "SELECT id FROM visits WHERE user_id=? AND visitor_id=? AND page=? "
            "AND visited_at > datetime('now','-30 minutes') LIMIT 1",
            (user_id, visitor_id, page)
        ).fetchone()
        if recent: return jsonify({'ok':True, 'throttled':True})

    db.execute(
        "INSERT INTO visits(user_id, visitor_id, page, project_id, country, device, referrer) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, visitor_id, page, project_id, country, device, referrer)
    )
    db.commit()
    return jsonify({'ok':True})


@app.route('/api/analytics')
@login_required
def get_analytics():
    user_id = uid()
    try: days = int(request.args.get('days', 30))
    except: days = 30
    if days not in (7, 30, 90, 365): days = 30
    range_clause = f"-{days} days"

    db = get_db()
    args = (user_id, range_clause)

    total_visits = db.execute(
        "SELECT COUNT(*) FROM visits WHERE user_id=? AND visited_at > datetime('now',?)", args
    ).fetchone()[0]

    unique_visitors = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) FROM visits "
        "WHERE user_id=? AND visited_at > datetime('now',?) AND visitor_id != ''", args
    ).fetchone()[0]

    daily = db.execute(
        "SELECT date(visited_at) AS day, COUNT(*) AS visits FROM visits "
        "WHERE user_id=? AND visited_at > datetime('now',?) "
        "GROUP BY day ORDER BY day ASC", args
    ).fetchall()

    top_projects = db.execute(
        "SELECT p.id, p.title, COUNT(v.id) AS views FROM visits v "
        "JOIN projects p ON p.id = v.project_id "
        "WHERE v.user_id=? AND v.project_id IS NOT NULL AND v.visited_at > datetime('now',?) "
        "GROUP BY p.id ORDER BY views DESC LIMIT 10", args
    ).fetchall()

    top_countries = db.execute(
        "SELECT country, COUNT(*) AS visits FROM visits "
        "WHERE user_id=? AND country != '' AND visited_at > datetime('now',?) "
        "GROUP BY country ORDER BY visits DESC LIMIT 10", args
    ).fetchall()

    devices = db.execute(
        "SELECT device, COUNT(*) AS visits FROM visits "
        "WHERE user_id=? AND visited_at > datetime('now',?) "
        "GROUP BY device", args
    ).fetchall()

    referrers = db.execute(
        "SELECT referrer, COUNT(*) AS visits FROM visits "
        "WHERE user_id=? AND referrer != '' AND visited_at > datetime('now',?) "
        "GROUP BY referrer ORDER BY visits DESC LIMIT 8", args
    ).fetchall()

    # Fill missing days with 0 (so chart is continuous)
    from datetime import datetime as _dt, timedelta as _td
    daily_map = {r['day']: r['visits'] for r in daily}
    today = _dt.utcnow().date()
    daily_full = []
    for i in range(days, -1, -1):
        d = (today - _td(days=i)).isoformat()
        daily_full.append({'day': d, 'visits': daily_map.get(d, 0)})

    return jsonify({
        'total_visits': total_visits,
        'unique_visitors': unique_visitors,
        'daily': daily_full,
        'top_projects': [dict(p) for p in top_projects],
        'top_countries': [dict(c) for c in top_countries],
        'devices': [dict(d) for d in devices],
        'referrers': [dict(r) for r in referrers],
    })

# ── STORAGE HELPERS ──
def upd_storage(user_id, delta_bytes, db):
    db.execute("UPDATE users SET storage_used_mb=MAX(0,storage_used_mb+?) WHERE id=?", (delta_bytes/1048576, user_id))

def chk_storage(user_id, size, db):
    u = db.execute("SELECT storage_limit_mb,storage_used_mb FROM users WHERE id=?", (user_id,)).fetchone()
    return u and (u['storage_used_mb'] + size/1048576) <= u['storage_limit_mb']

# ── FILE HANDLING ──
ALLOWED_IMG = {'jpg','jpeg','png','gif','webp'}
ALLOWED_VID = {'mp4','mov','webm','avi'}
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

@app.errorhandler(413)
def too_large(e): return jsonify({'error':'الملف كبير جداً'}), 413

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def optimize_image(path, max_dim=1920, q=82):
    if not HAS_PIL: return
    try:
        ext = path.rsplit('.',1)[-1].lower()
        if ext in ('gif','svg'): return
        img = ImageOps.exif_transpose(Image.open(path))
        if ext in ('jpg','jpeg') and img.mode in ('RGBA','P'):
            bg = Image.new('RGB', img.size, (255,255,255))
            bg.paste(img, mask=img.split()[-1] if img.mode=='RGBA' else None)
            img = bg
        if img.width > max_dim or img.height > max_dim: img.thumbnail((max_dim,max_dim), Image.LANCZOS)
        kw = {'optimize':True}
        if ext in ('jpg','jpeg'): kw.update({'quality':q,'progressive':True})
        elif ext == 'webp': kw.update({'quality':q,'method':6})
        elif ext == 'png': kw['compress_level'] = 7
        img.save(path, **kw)
    except Exception as e: print(f'optimize error: {e}')

def save_dataurl(dataurl, allowed, user_id=None):
    if not dataurl or not isinstance(dataurl, str): return None
    m = re.match(r'data:([^;]+);base64,(.+)', dataurl, re.DOTALL)
    if not m: return None
    mime, b64 = m.group(1), m.group(2)
    ext = {'image/jpeg':'jpg','image/jpg':'jpg','image/png':'png','image/gif':'gif','image/webp':'webp',
           'image/heic':'jpg','image/heif':'jpg','video/mp4':'mp4','video/quicktime':'mov',
           'video/webm':'webm','video/avi':'avi'}.get(mime.lower(),'bin')
    if ext not in allowed: return None
    try:
        raw = base64.b64decode(b64)
        if user_id:
            db = get_db()
            if not chk_storage(user_id, len(raw), db): return '__STORAGE_LIMIT__'
        fname = f'{uuid.uuid4().hex}.{ext}'
        fpath = os.path.join(UPLOAD_DIR, fname)
        with open(fpath,'wb') as f: f.write(raw)
        if ext in ('jpg','jpeg','png','webp'): optimize_image(fpath)
        if user_id:
            db = get_db(); upd_storage(user_id, os.path.getsize(fpath), db); db.commit()
        return f'/uploads/{fname}'
    except Exception as e: print(f'save_dataurl: {e}'); return None

def delete_file(url, user_id=None):
    if url and url.startswith('/uploads/'):
        p = os.path.join(UPLOAD_DIR, os.path.basename(url))
        if os.path.exists(p):
            sz = os.path.getsize(p)
            os.remove(p)
            if user_id:
                db = get_db(); upd_storage(user_id, -sz, db); db.commit()

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files: return jsonify({'error':'لا يوجد ملف'}), 400
    f = request.files['file']
    kind = request.form.get('kind','image')
    allowed = ALLOWED_VID if kind=='video' else ALLOWED_IMG
    ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
    if ext in ('heic','heif'): ext = 'jpg'
    if ext not in allowed: return jsonify({'error':f'نوع غير مسموح: {ext}'}), 400
    user_id = uid()
    db = get_db()
    f.seek(0,2); sz = f.tell(); f.seek(0)
    if not chk_storage(user_id, sz, db): return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
    fname = f'{uuid.uuid4().hex}.{ext}'
    fpath = os.path.join(UPLOAD_DIR, fname)
    try:
        f.save(fpath)
        if kind != 'video': optimize_image(fpath)
        upd_storage(user_id, os.path.getsize(fpath), db); db.commit()
        return jsonify({'url':f'/uploads/{fname}'})
    except Exception as e: return jsonify({'error':str(e)}), 500

# ── PROJECTS ──
def fix_modules(mods, pid, db, user_id):
    changed, out = False, []
    for mod in mods or []:
        if not isinstance(mod, dict): out.append(mod); continue
        mod = dict(mod)
        if mod.get('type') == 'image' and isinstance(mod.get('src',''), str) and mod['src'].startswith('data:'):
            url = save_dataurl(mod['src'], ALLOWED_IMG, user_id)
            if url and url != '__STORAGE_LIMIT__': mod['src'] = url; changed = True
        elif mod.get('type') in ('photo-grid','grid'):
            items = []
            for item in mod.get('items',[]) or []:
                item = dict(item) if isinstance(item,dict) else {}
                if isinstance(item.get('src',''),str) and item.get('src','').startswith('data:'):
                    url = save_dataurl(item['src'], ALLOWED_IMG, user_id)
                    if url and url != '__STORAGE_LIMIT__': item['src'] = url; changed = True
                items.append(item)
            mod['items'] = items
        out.append(mod)
    if changed:
        try: db.execute('UPDATE projects SET modules=? WHERE id=?', (json.dumps(out), pid)); db.commit()
        except: pass
    return out

def proj_dict(row, db):
    imgs = db.execute('SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order', (row['id'],)).fetchall()
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    mods = fix_modules(mods, row['id'], db, row['user_id'])
    def _col(name, default):
        try: return row[name] or default
        except: return default
    return {'id':row['id'],'title':row['title'],'category':row['category'],'description':row['description'] or '',
            'mediaType':row['media_type'],'coverImage':row['cover_url'],'videoUrl':row['video_url'],
            'images':[r['url'] for r in imgs],'date':row['created_at'][:10],
            'projectType':row['project_type'] or 'grid',
            'aspectRatio':_col('aspect_ratio','9:16'),
            'videoKind':_col('video_kind','reel'),
            'modules':mods}

@app.route('/api/projects')
def get_projects():
    # If URL explicitly specifies user_id, use it (public viewing)
    # Otherwise use session (admin viewing own projects)
    uid_p = request.args.get('user_id')
    if uid_p:
        try: user_id = int(uid_p)
        except: user_id = None
    else:
        user_id = session.get('user_id')
    if not user_id:
        owner = get_db().execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        user_id = owner['id'] if owner else 1
    db = get_db()
    rows = db.execute('SELECT * FROM projects WHERE user_id=? ORDER BY sort_order DESC, id DESC', (user_id,)).fetchall()
    return jsonify([proj_dict(r, db) for r in rows])

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    user_id = uid()
    d = request.get_json()
    title = (d.get('title') or '').strip()
    if not title: return jsonify({'error':'العنوان مطلوب'}), 400
    cov = d.get('coverImage')
    if cov and cov.startswith('data:'):
        cover_url = save_dataurl(cov, ALLOWED_IMG, user_id)
        if cover_url == '__STORAGE_LIMIT__': return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
    elif cov and cov.startswith('/uploads/'): cover_url = cov
    elif cov and cov.startswith(('http://','https://')):
        # External URL (auto-fetched thumbnail) — try download, fallback to URL
        try:
            r2 = proxy_one(cov)
            if r2 and r2.startswith('data:'):
                saved = save_dataurl(r2, ALLOWED_IMG, user_id)
                cover_url = cov if saved == '__STORAGE_LIMIT__' else saved
            else: cover_url = cov
        except: cover_url = cov
    else: cover_url = None
    embed = d.get('embedUrl')
    if embed: video_url = embed
    else:
        vd = d.get('videoData')
        if vd and vd.startswith('data:'):
            video_url = save_dataurl(vd, ALLOWED_VID, user_id)
            if video_url == '__STORAGE_LIMIT__': return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
        elif vd and vd.startswith('/uploads/'): video_url = vd
        else: video_url = None
    db = get_db()
    # New projects appear first
    mx = db.execute('SELECT COALESCE(MAX(sort_order),0) AS m FROM projects WHERE user_id=?', (user_id,)).fetchone()
    next_sort = (mx['m'] if mx else 0) + 1
    aspect_ratio = d.get('aspectRatio', '9:16')
    video_kind   = d.get('videoKind', 'reel')
    cur = db.execute('INSERT INTO projects(user_id,title,category,description,media_type,cover_url,video_url,project_type,sort_order,aspect_ratio,video_kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (user_id, title, d.get('category','Social Media'), d.get('description',''), d.get('mediaType','image'), cover_url, video_url, d.get('projectType','grid'), next_sort, aspect_ratio, video_kind))
    pid = cur.lastrowid
    for i, img in enumerate(d.get('images',[])):
        url = save_dataurl(img, ALLOWED_IMG, user_id) if img.startswith('data:') else (img if img.startswith('/uploads/') else None)
        if url and url != '__STORAGE_LIMIT__':
            db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,url,i))
    db.commit()
    return jsonify(proj_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(), db)), 201

@app.route('/api/projects/<int:pid>', methods=['PUT'])
@login_required
def update_project(pid):
    user_id = uid()
    db = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, user_id)).fetchone()
    if not row: abort(404)
    d = request.get_json()
    def resolve(field, old, allowed):
        v = d.get(field)
        if v is None: return old
        if v == '': delete_file(old, user_id); return None
        if v.startswith('data:'):
            delete_file(old, user_id)
            url = save_dataurl(v, allowed, user_id)
            return None if url == '__STORAGE_LIMIT__' else url
        if v.startswith('/uploads/'):
            if v != old: delete_file(old, user_id)
            return v
        if v.startswith(('http://','https://')):
            try:
                r2 = proxy_one(v)
                if r2 and r2.startswith('data:'):
                    delete_file(old, user_id)
                    url = save_dataurl(r2, allowed, user_id)
                    return v if url == '__STORAGE_LIMIT__' else url
            except: pass
            return v
        return old
    cover_url = resolve('coverImage', row['cover_url'], ALLOWED_IMG)
    if d.get('embedUrl'):
        if row['video_url'] and not row['video_url'].startswith('http'): delete_file(row['video_url'], user_id)
        video_url = d['embedUrl']
    else: video_url = resolve('videoData', row['video_url'], ALLOWED_VID)
    db.execute('UPDATE projects SET title=?,category=?,description=?,media_type=?,cover_url=?,video_url=? WHERE id=?',
        ((d.get('title') or row['title']).strip(), d.get('category',row['category']),
         d.get('description',row['description']), d.get('mediaType',row['media_type']), cover_url, video_url, pid))
    if 'projectType' in d: db.execute('UPDATE projects SET project_type=? WHERE id=?', (d['projectType'], pid))
    if 'aspectRatio' in d: db.execute('UPDATE projects SET aspect_ratio=? WHERE id=?', (d['aspectRatio'], pid))
    if 'videoKind' in d: db.execute('UPDATE projects SET video_kind=? WHERE id=?', (d['videoKind'], pid))
    keep = d.get('keepImages') or []; new_imgs = d.get('images') or []
    if 'keepImages' in d or 'images' in d:
        kept = set(keep)
        for o in db.execute('SELECT url FROM project_images WHERE project_id=?', (pid,)).fetchall():
            if o['url'] not in kept: delete_file(o['url'], user_id)
        db.execute('DELETE FROM project_images WHERE project_id=?', (pid,))
        for i, u in enumerate(keep):
            db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,u,i))
        for i, img in enumerate(new_imgs):
            if not img: continue
            url = save_dataurl(img, ALLOWED_IMG, user_id) if img.startswith('data:') else (img if img.startswith('/uploads/') else None)
            if url and url != '__STORAGE_LIMIT__':
                db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,url,len(keep)+i))
    ptype = d.get('projectType', row['project_type'] or 'grid')
    if ptype == 'grid' and d.get('mediaType','image') != 'video':
        imgs = db.execute('SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order', (pid,)).fetchall()
        db.execute('UPDATE projects SET modules=? WHERE id=?', (json.dumps([{'type':'image','src':r['url']} for r in imgs if r['url']]), pid))
    db.commit()
    return jsonify(proj_dict(db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone(), db))

@app.route('/api/projects/<int:pid>', methods=['DELETE'])
@login_required
def delete_project(pid):
    user_id = uid()
    db = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, user_id)).fetchone()
    if not row: abort(404)
    delete_file(row['cover_url'], user_id); delete_file(row['video_url'], user_id)
    for img in db.execute('SELECT url FROM project_images WHERE project_id=?', (pid,)).fetchall():
        delete_file(img['url'], user_id)
    db.execute('DELETE FROM projects WHERE id=?', (pid,)); db.commit()
    return jsonify({'ok':True})

@app.route('/api/projects/reorder', methods=['PUT'])
@login_required
def reorder_projects():
    user_id = uid()
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'ids must be a non-empty list'}), 400
    db = get_db()
    # First id gets the highest sort_order so it appears first (GET uses ORDER BY sort_order DESC)
    n = len(ids)
    for i, pid in enumerate(ids):
        try:
            db.execute('UPDATE projects SET sort_order=? WHERE id=? AND user_id=?',
                       (n - i, int(pid), user_id))
        except (ValueError, TypeError):
            continue
    db.commit()
    return jsonify({'ok': True, 'count': n})

@app.route('/api/projects/<int:pid>/modules', methods=['GET'])
@login_required
def get_modules(pid):
    user_id = uid(); db = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, user_id)).fetchone()
    if not row: abort(404)
    mods = []
    try: mods = json.loads(row['modules'] or '[]')
    except: pass
    return jsonify({'modules':mods,'project':proj_dict(row, db)})

@app.route('/api/projects/<int:pid>/modules', methods=['PUT'])
@login_required
def save_modules(pid):
    user_id = uid(); db = get_db()
    row = db.execute('SELECT * FROM projects WHERE id=? AND user_id=?', (pid, user_id)).fetchone()
    if not row: abort(404)
    d = request.get_json(); modules = d.get('modules', []); ptype = d.get('projectType', row['project_type'] or 'grid')
    processed = []
    for mod in modules:
        mod = dict(mod)
        if mod.get('type') == 'image' and mod.get('src','').startswith('data:'):
            url = save_dataurl(mod['src'], ALLOWED_IMG, user_id)
            if url == '__STORAGE_LIMIT__': return jsonify({'error':'⚠️ وصلت للحد الأقصى'}), 400
            mod['src'] = url or mod['src']
        elif mod.get('type') in ('photo-grid','grid'):
            items = []
            for item in mod.get('items',[]) or []:
                item = dict(item) if isinstance(item,dict) else {}
                if item.get('src','').startswith('data:'):
                    url = save_dataurl(item['src'], ALLOWED_IMG, user_id)
                    if url == '__STORAGE_LIMIT__': return jsonify({'error':'⚠️ وصلت للحد الأقصى'}), 400
                    item['src'] = url or item['src']
                items.append(item)
            mod['items'] = items
        processed.append(mod)
    db.execute('UPDATE projects SET modules=?,project_type=? WHERE id=?', (json.dumps(processed), ptype, pid))
    if ptype == 'grid':
        img_mods = [m for m in processed if m.get('type')=='image' and m.get('src')]
        if img_mods:
            db.execute('DELETE FROM project_images WHERE project_id=?', (pid,))
            for i, m in enumerate(img_mods):
                db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)', (pid,m['src'],i))
    db.commit(); return jsonify({'ok':True,'modules':processed})

# ── SETTINGS ──
@app.route('/api/settings')
def get_settings():
    # URL user_id parameter takes priority over session (for public viewing)
    uid_p = request.args.get('user_id')
    if uid_p:
        try: user_id = int(uid_p)
        except: user_id = None
    else:
        user_id = session.get('user_id')
    if not user_id:
        owner = get_db().execute("SELECT id FROM users WHERE is_owner=1").fetchone()
        user_id = owner['id'] if owner else 1
    db = get_db()
    rows = db.execute('SELECT key,value FROM settings WHERE user_id=?', (user_id,)).fetchall()
    out = {}
    for r in rows:
        try: out[r['key']] = json.loads(r['value'])
        except: out[r['key']] = r['value']

    # Auto-migrate sections: add logos & testimonials if missing (for existing users)
    try:
        secs = out.get('sections')
        if isinstance(secs, list):
            existing_ids = {s.get('id') for s in secs if isinstance(s, dict)}
            changed = False
            if 'logos' not in existing_ids:
                # Insert before contact, or at end
                contact_idx = next((i for i,s in enumerate(secs) if s.get('id')=='contact'), len(secs))
                secs.insert(contact_idx, {"id":"logos","label_ar":"العملاء","label_en":"Clients","visible":True,"order":contact_idx})
                changed = True
            if 'testimonials' not in existing_ids:
                contact_idx = next((i for i,s in enumerate(secs) if s.get('id')=='contact'), len(secs))
                secs.insert(contact_idx, {"id":"testimonials","label_ar":"آراء العملاء","label_en":"Testimonials","visible":True,"order":contact_idx})
                changed = True
            if 'achievements' not in existing_ids:
                contact_idx = next((i for i,s in enumerate(secs) if s.get('id')=='contact'), len(secs))
                secs.insert(contact_idx, {"id":"achievements","label_ar":"الإنجازات","label_en":"Achievements","visible":True,"order":contact_idx})
                changed = True
            if changed:
                # Re-number orders
                for i, s in enumerate(secs):
                    if isinstance(s, dict): s['order'] = i
                # Save back (only if user is owner of these settings)
                if session.get('user_id') == user_id:
                    db.execute("INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)",
                               (user_id, 'sections', json.dumps(secs)))
                    db.commit()
                out['sections'] = secs
    except Exception as e:
        print(f'sections migration error: {e}')

    return jsonify(out)

@app.route('/api/settings', methods=['PUT'])
@login_required
def update_settings():
    user_id = uid(); d = request.get_json(); db = get_db()
    for upload_key, store_key in [('photo_upload','photo_url'),('hero_cover_upload','hero_cover_url'),('brand_logo_upload','brand_logo_url'),('favicon_upload','favicon_url')]:
        img = d.pop(upload_key, None)
        if img and isinstance(img,str) and img.startswith('data:'):
            old = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (user_id,store_key)).fetchone()
            if old and old['value']: delete_file(old['value'], user_id)
            url = save_dataurl(img, ALLOWED_IMG, user_id)
            if url == '__STORAGE_LIMIT__': return jsonify({'error':'⚠️ وصلت للحد الأقصى'}), 400
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,store_key,url or ''))
        elif img and isinstance(img,str) and img.startswith('/uploads/'):
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,store_key,img))
        elif img == '':
            old = db.execute("SELECT value FROM settings WHERE user_id=? AND key=?", (user_id,store_key)).fetchone()
            if old and old['value']: delete_file(old['value'], user_id)
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,store_key,''))
    tool_imgs = {k:v for k,v in d.items() if k.startswith('tool_img_upload_')}
    for k in tool_imgs: d.pop(k)
    for k, img in tool_imgs.items():
        if img and img.startswith('data:'):
            url = save_dataurl(img, ALLOWED_IMG, user_id)
            if url and url != '__STORAGE_LIMIT__':
                db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,k.replace('upload','url'),url))
        elif img == '':
            db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,k.replace('upload','url'),''))
    for k, v in d.items():
        val = json.dumps(v) if isinstance(v,(dict,list)) else str(v)
        db.execute('INSERT OR REPLACE INTO settings(user_id,key,value) VALUES(?,?,?)', (user_id,k,val))
    db.commit(); return jsonify({'ok':True})

@app.route('/api/auth/credentials', methods=['PUT'])
@login_required
def change_credentials():
    user_id = uid(); d = request.get_json() or {}
    new_user = d.get('username','').strip(); new_pass = d.get('password','').strip(); old_pass = d.get('old_password','').strip()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or old_pass != user['password']: return jsonify({'error':'كلمة المرور الحالية غير صحيحة'}), 403
    if not new_user or not new_pass: return jsonify({'error':'أدخل اسم المستخدم وكلمة المرور'}), 400
    if len(new_pass) < 6: return jsonify({'error':'كلمة المرور 6 أحرف على الأقل'}), 400
    db.execute("UPDATE users SET username=?,password=? WHERE id=?", (new_user,new_pass,user_id))
    db.commit(); session['username'] = new_user; return jsonify({'ok':True})

# ── IMPORT UTILITIES ──
import urllib.request, urllib.error, html as html_mod, gzip, io

# Realistic browser headers — bypasses most anti-bot checks
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

def fetch_url(url, timeout=15, extra_headers=None):
    headers = dict(BROWSER_HEADERS)
    if extra_headers: headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding','').lower() == 'gzip':
            try: raw = gzip.decompress(raw)
            except: pass
        return raw.decode('utf-8','replace'), r.headers.get_content_type()

def fetch_url_with_fallback(url, timeout=15):
    """Try multiple strategies to bypass anti-bot. Returns (body, error_msg)."""
    strategies = [
        # Strategy 1: Desktop Safari
        {'name':'safari', 'headers': dict(BROWSER_HEADERS)},
        # Strategy 2: Mobile iPhone
        {'name':'mobile', 'headers': {**BROWSER_HEADERS, 'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'}},
        # Strategy 3: Googlebot (most sites whitelist this)
        {'name':'googlebot', 'headers': {**BROWSER_HEADERS, 'User-Agent':'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}},
    ]

    last_error = None
    for s in strategies:
        try:
            req = urllib.request.Request(url, headers=s['headers'])
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding','').lower() == 'gzip':
                    try: raw = gzip.decompress(raw)
                    except: pass
                return raw.decode('utf-8','replace'), None
        except urllib.error.HTTPError as e:
            last_error = e
            time.sleep(0.5)  # brief delay before retry
            continue
        except Exception as e:
            last_error = e
            continue
    return None, last_error

def proxy_one(url):
    headers = dict(BROWSER_HEADERS)
    headers['Referer'] = 'https://www.behance.net/'
    headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        if resp.headers.get('Content-Encoding','').lower() == 'gzip':
            try: raw = gzip.decompress(raw)
            except: pass
        ct = resp.headers.get_content_type() or 'image/jpeg'
        return f'data:{ct};base64,{base64.b64encode(raw).decode()}'

@app.route('/api/proxy-image', methods=['POST'])
@login_required
def proxy_image():
    url = (request.get_json() or {}).get('url','').strip()
    if not url or not url.startswith('http'): return jsonify({'error':'invalid url'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            ct = resp.headers.get_content_type() or 'image/jpeg'
            return jsonify({'dataUrl':f'data:{ct};base64,{base64.b64encode(resp.read()).decode()}'})
    except Exception as e: return jsonify({'error':str(e)}), 500

@app.route('/api/proxy-images', methods=['POST'])
@login_required
def proxy_images():
    urls = (request.get_json() or {}).get('urls',[])[:12]
    results = []
    for url in urls:
        try: results.append(proxy_one(url))
        except: results.append(None)
    return jsonify({'images':results})

@app.route('/api/import/save-images', methods=['POST'])
@login_required
def import_save_images():
    """Download images from URLs (using Behance referer headers) and save to disk.
    Returns URL paths. Avoids huge base64 payloads in subsequent project save."""
    urls = (request.get_json() or {}).get('urls',[])[:60]
    if not urls: return jsonify({'images': []})
    user_id = uid()
    db = get_db()
    user = db.execute("SELECT storage_limit_mb, storage_used_mb FROM users WHERE id=?", (user_id,)).fetchone()
    available_bytes = ((user['storage_limit_mb'] or 0) - (user['storage_used_mb'] or 0)) * 1024 * 1024

    # Same headers as proxy_one (which works)
    headers = dict(BROWSER_HEADERS)
    headers['Referer'] = 'https://www.behance.net/'
    headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'

    def try_download(url):
        """Try downloading, with fallback to lower resolutions if /source/ fails."""
        attempts = [url]
        # If URL has /source/, try /max_3840/ and /max_1200/ as fallbacks
        if '/source/' in url:
            attempts.append(url.replace('/source/', '/max_3840/'))
            attempts.append(url.replace('/source/', '/max_1200/'))
            attempts.append(url.replace('/source/', '/disp/'))

        last_err = None
        for attempt_url in attempts:
            try:
                req = urllib.request.Request(attempt_url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    content = resp.read()
                    if resp.headers.get('Content-Encoding','').lower() == 'gzip':
                        try: content = gzip.decompress(content)
                        except: pass
                    ct = (resp.headers.get_content_type() or 'image/jpeg').lower()
                    if len(content) >= 1024:
                        return content, ct, attempt_url
            except Exception as e:
                last_err = str(e)
                continue
        return None, None, last_err

    results = []
    total_bytes = 0
    success_count = 0
    fail_count = 0
    fail_log = []

    for url in urls:
        try:
            if not isinstance(url, str):
                results.append(None); fail_count += 1
                fail_log.append('not a string')
                continue

            content = None
            ct = 'image/jpeg'

            # Handle base64 data URLs (from bookmarklet client-side conversion)
            if url.startswith('data:'):
                try:
                    header, b64data = url.split(',', 1)
                    # Extract content type
                    if ';' in header:
                        mt = header.split(':')[1].split(';')[0]
                        if mt: ct = mt.lower()
                    content = base64.b64decode(b64data)
                except Exception as e:
                    print(f'base64 decode failed: {e}')
                    results.append(None); fail_count += 1
                    fail_log.append(f'base64 decode: {e}')
                    continue
            elif url.startswith('http'):
                # Download from URL
                content_data, ct_dl, info = try_download(url)
                if content_data:
                    content = content_data
                    if ct_dl: ct = ct_dl
                else:
                    results.append(None); fail_count += 1
                    fail_log.append(f'http fail for {url[:80]}: {info}')
                    continue
            else:
                results.append(None); fail_count += 1
                fail_log.append(f'invalid scheme: {url[:50]}')
                continue

            if not content or len(content) < 1024:
                results.append(None); fail_count += 1
                fail_log.append('content too small')
                continue

            if total_bytes + len(content) > available_bytes:
                results.append(None); fail_count += 1
                fail_log.append('storage limit reached')
                continue

            # Save as WebP for smaller size & better web performance
            ts = int(time.time() * 1000) + len(results)
            fname = f"u{user_id}_bh_{ts}.webp"
            fpath = os.path.join(UPLOAD_DIR, fname)

            # First write raw content, then convert to webp
            tmp_path = fpath + '.tmp'
            with open(tmp_path, 'wb') as fp: fp.write(content)

            converted = False
            if HAS_PIL:
                try:
                    img = ImageOps.exif_transpose(Image.open(tmp_path))
                    # Convert RGBA/P → RGB for non-transparent images
                    if img.mode == 'P':
                        img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
                    if img.width > 1920 or img.height > 1920:
                        img.thumbnail((1920, 1920), Image.LANCZOS)
                    # Save as webp with good quality
                    img.save(fpath, 'WEBP', quality=82, method=6)
                    os.remove(tmp_path)
                    converted = True
                except Exception as e:
                    print(f'webp conversion failed: {e}, falling back to original')
                    converted = False

            if not converted:
                # Fallback: keep original format
                ext_map = {'image/jpeg':'jpg','image/jpg':'jpg','image/png':'png',
                           'image/webp':'webp','image/gif':'gif'}
                ext = ext_map.get(ct, 'jpg')
                fname = f"u{user_id}_bh_{ts}.{ext}"
                fpath_fallback = os.path.join(UPLOAD_DIR, fname)
                shutil.move(tmp_path, fpath_fallback)
                fpath = fpath_fallback
                if ext in ('jpg','jpeg','png','webp'):
                    try: optimize_image(fpath)
                    except Exception as oe: print(f'optimize failed: {oe}')

            file_size = os.path.getsize(fpath)
            total_bytes += file_size
            success_count += 1
            results.append(f'/uploads/{fname}')

        except Exception as e:
            print(f'save-images outer error: {e}')
            fail_count += 1
            fail_log.append(f'outer: {e}')
            results.append(None)

    if total_bytes:
        upd_storage(user_id, total_bytes, db)
        db.commit()

    print(f'[import] {success_count}/{len(urls)} saved, {fail_count} failed, {round(total_bytes/(1024*1024),2)} MB')
    if fail_log: print(f'[import] fails: {fail_log[:3]}')
    return jsonify({'images': results, 'total_mb': round(total_bytes/(1024*1024), 2),
                    'saved': success_count, 'failed': fail_count})

@app.route('/api/vimeo/fetch', methods=['POST'])
@login_required
def vimeo_fetch():
    url = (request.get_json() or {}).get('url','').strip()
    m = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
    if not m: return jsonify({'error':'رابط Vimeo غير صحيح'}), 400
    vid_id = m.group(1)
    try:
        body, _ = fetch_url(f'https://vimeo.com/api/oembed.json?url=https://vimeo.com/{vid_id}&width=640')
        oe = json.loads(body)
        return jsonify({'id':vid_id,'title':oe.get('title',''),'description':oe.get('description','') or '',
                       'thumbnail':oe.get('thumbnail_url',''),'duration':oe.get('duration',0),
                       'embed_url':f'https://player.vimeo.com/video/{vid_id}?portrait=0&byline=0&title=0'})
    except Exception as e: return jsonify({'error':str(e)}), 502

@app.route('/api/video/thumbnail', methods=['POST'])
@login_required
def video_thumbnail():
    """Fetch video thumbnail from YouTube/Vimeo (oEmbed) or generic og:image."""
    url = (request.get_json() or {}).get('url','').strip()
    if not url: return jsonify({'error':'no url','thumbnail':'','title':''}), 200
    try:
        # YouTube
        yt = re.search(r'(?:youtube\.com/(?:watch\?v=|shorts/|embed/|v/)|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
        if yt:
            vid = yt.group(1)
            thumb = f'https://i.ytimg.com/vi/{vid}/maxresdefault.jpg'
            title = ''
            try:
                body, _ = fetch_url(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json')
                oe = json.loads(body)
                title = oe.get('title','')
                if oe.get('thumbnail_url'): thumb = oe['thumbnail_url']
            except: pass
            return jsonify({'thumbnail': thumb, 'title': title})
        # Vimeo
        vm = re.search(r'vimeo\.com/(?:video/)?(\d+)', url)
        if vm:
            vid = vm.group(1)
            body, _ = fetch_url(f'https://vimeo.com/api/oembed.json?url=https://vimeo.com/{vid}&width=640')
            oe = json.loads(body)
            return jsonify({'thumbnail': oe.get('thumbnail_url',''), 'title': oe.get('title','')})
        # Generic og:image fallback
        try:
            body, _ = fetch_url(url)
            og = re.search(r'<meta property="og:image"\s+content="([^"]+)"', body or '')
            if og:
                return jsonify({'thumbnail': html_mod.unescape(og.group(1)), 'title': ''})
        except: pass
        return jsonify({'thumbnail':'', 'title':''})
    except Exception as e:
        return jsonify({'error': str(e), 'thumbnail':'', 'title':''}), 200
# Bookmarklet runs in user's browser on Behance, sends data via POST,
# then redirects user back to admin with import_id in URL.

_pending_imports = {}  # {import_id: {data, expires_at}}

@app.route('/bookmarklet.js')
def bookmarklet_js():
    """JS file run inside Behance's page context. Extracts content and posts to our API."""
    base = request.host_url.rstrip('/')
    js = f'''(function(){{
  if(!location.host.includes('behance.net')){{
    alert('⚠️ هذا الزر يعمل فقط على صفحات Behance');
    return;
  }}

  // Show progress overlay
  var overlay = document.createElement('div');
  overlay.id = '__bh_overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:999999;display:flex;align-items:center;justify-content:center;color:#fff;font-family:Arial,sans-serif;font-size:18px;flex-direction:column;';
  overlay.innerHTML = '<div style="background:#1769ff;padding:30px 50px;border-radius:12px;text-align:center;"><div id="__bh_msg" style="font-size:18px;font-weight:bold;margin-bottom:14px;">⏳ جاري التحضير...</div><div id="__bh_sub" style="font-size:13px;opacity:0.8;">يرجى عدم التحرك</div></div>';
  document.body.appendChild(overlay);
  var setMsg = function(m, s){{ var el=document.getElementById('__bh_msg'); if(el) el.textContent=m; var es=document.getElementById('__bh_sub'); if(es && s!==undefined) es.textContent=s; }};
  var removeOverlay = function(){{ try{{ document.body.removeChild(overlay); }}catch(e){{}} }};

  // Cache images as we scroll (Behance may dispose images that leave viewport)
  var imageCache = {{}};  // key → {{src, y, x, width, height}}
  var bgCache = {{}};

  function captureImagesNow(){{
    // Capture all visible images (including from <picture> srcset)
    var imgs = document.querySelectorAll('img');
    for(var i=0; i<imgs.length; i++){{
      var node = imgs[i];
      var src = node.currentSrc || node.src || node.getAttribute('data-src') || node.getAttribute('data-lazy-src') || '';
      // Try srcset if regular src didn't match
      if(!isBehanceProjectImage(src)){{
        var srcset = node.srcset || node.getAttribute('data-srcset') || '';
        if(srcset){{
          // Parse srcset, get last (largest) URL
          var parts = srcset.split(',');
          for(var p=parts.length-1; p>=0; p--){{
            var url = parts[p].trim().split(' ')[0];
            if(isBehanceProjectImage(url)){{ src = url; break; }}
          }}
        }}
      }}
      if(!isBehanceProjectImage(src)) continue;
      var hires = upgradeRes(src);
      var key = hires.split('?')[0];
      if(imageCache[key]) continue;
      var rect = node.getBoundingClientRect();
      if(rect.width < 50 || rect.height < 50) continue;
      imageCache[key] = {{
        src: hires,
        y: rect.top + window.scrollY,
        x: rect.left,
        width: rect.width,
        height: rect.height
      }};
    }}
    // Capture <source> tags inside <picture>
    var sources = document.querySelectorAll('source[srcset]');
    for(var i=0; i<sources.length; i++){{
      var srcset = sources[i].srcset || '';
      var parts = srcset.split(',');
      for(var p=parts.length-1; p>=0; p--){{
        var url = parts[p].trim().split(' ')[0];
        if(!isBehanceProjectImage(url)) continue;
        var hires = upgradeRes(url);
        var key = hires.split('?')[0];
        if(imageCache[key]) continue;
        var pict = sources[i].parentElement;
        var rect = pict ? pict.getBoundingClientRect() : {{top:0,left:0,width:200,height:200}};
        if(rect.width < 50 || rect.height < 50) continue;
        imageCache[key] = {{
          src: hires,
          y: rect.top + window.scrollY,
          x: rect.left,
          width: rect.width,
          height: rect.height
        }};
        break;
      }}
    }}
    // Capture background-image elements
    var bgEls = document.querySelectorAll('[style*="background"], [class*="image"], [class*="Image"], [class*="grid"], [class*="Grid"], [class*="module"], [class*="Module"]');
    for(var i=0; i<bgEls.length; i++){{
      var el = bgEls[i];
      var bg = getBgImage(el);
      if(!bg || !isBehanceProjectImage(bg)) continue;
      var hires = upgradeRes(bg);
      var key = hires.split('?')[0];
      if(imageCache[key] || bgCache[key]) continue;
      var rect = el.getBoundingClientRect();
      if(rect.width < 100 || rect.height < 100) continue;
      bgCache[key] = {{
        src: hires,
        y: rect.top + window.scrollY,
        x: rect.left,
        width: rect.width,
        height: rect.height
      }};
    }}
  }}

  // Smart auto-scroll: wait for images to actually load between scroll steps
  setMsg('⏳ جاري تحميل كل الصور...', 'الخطوة 1 من 2: التمرير لأسفل');
  var step = window.innerHeight * 0.4;  // smaller steps for thoroughness
  captureImagesNow();

  function waitForImagesToLoad(timeoutMs){{
    return new Promise(function(resolve){{
      var imgs = document.querySelectorAll('img');
      var pending = 0;
      for(var i=0; i<imgs.length; i++){{
        var img = imgs[i];
        if(!img.complete && img.src){{ pending++; }}
      }}
      if(pending === 0){{ setTimeout(resolve, 200); return; }}
      // Wait for images or timeout
      var done = false;
      var timeout = setTimeout(function(){{ if(!done){{ done = true; resolve(); }} }}, timeoutMs);
      var checkInterval = setInterval(function(){{
        var stillPending = 0;
        var imgs2 = document.querySelectorAll('img');
        for(var i=0; i<imgs2.length; i++){{
          if(!imgs2[i].complete && imgs2[i].src) stillPending++;
        }}
        if(stillPending === 0 && !done){{
          done = true;
          clearInterval(checkInterval);
          clearTimeout(timeout);
          setTimeout(resolve, 300);  // small buffer
        }}
      }}, 200);
    }});
  }}

  async function smartScroll(){{
    // Pass 1: scroll down, waiting for images at each step
    var pos = 0;
    var totalHeight = document.body.scrollHeight;
    var stepCount = Math.ceil(totalHeight / step);
    var current = 0;
    while(pos < document.body.scrollHeight + 200){{
      current++;
      pos += step;
      window.scrollTo(0, pos);
      setMsg('⏳ جاري تحميل الصور...', 'تمرير ' + current + '/' + (stepCount + 2) + ' — انتظار التحميل');
      await waitForImagesToLoad(2500);  // wait up to 2.5s for images
      captureImagesNow();
      // Update height in case page grew (lazy loaded sections)
      if(document.body.scrollHeight > totalHeight){{
        totalHeight = document.body.scrollHeight;
        stepCount = Math.ceil(totalHeight / step);
      }}
    }}

    // Pass 2: scroll back up, capturing images that may have re-rendered
    setMsg('⏳ جاري المرور النهائي...', 'الخطوة 2 من 2: التحقق');
    var backPos = document.body.scrollHeight;
    while(backPos > 0){{
      backPos -= step * 1.5;  // bigger steps on the way up
      window.scrollTo(0, Math.max(0, backPos));
      await new Promise(r => setTimeout(r, 400));
      captureImagesNow();
    }}

    // Final: back to top and extract
    window.scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 800));
    captureImagesNow();  // final capture
    extractContent();
  }}
  smartScroll();

  function upgradeRes(src){{
    if(!src) return src;
    return src.replace(/\\/(disp|115|202|404|disp_500|max_1200|max_3840)\\//g, '/source/');
  }}

  function getBgImage(el){{
    // 1. Inline style
    var style = el.getAttribute('style') || '';
    var m = style.match(/background(?:-image)?\\s*:\\s*url\\(["']?([^"')]+)["']?\\)/);
    if(m) return m[1];
    // 2. Computed style (slower but catches CSS-defined backgrounds)
    try{{
      var cs = window.getComputedStyle(el);
      var bg = cs.getPropertyValue('background-image');
      if(bg && bg !== 'none'){{
        var m2 = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
        if(m2) return m2[1];
      }}
    }}catch(e){{}}
    return null;
  }}

  function isBehanceProjectImage(src){{
    if(!src || src.indexOf('http') !== 0) return false;
    // Skip data URLs, gifs of small icons, profile pics
    if(src.indexOf('data:') === 0) return false;
    if(src.indexOf('/profiles/') > -1) return false;
    if(src.indexOf('/users/') > -1) return false;
    if(src.indexOf('avatar') > -1) return false;
    // Behance CDNs
    return src.indexOf('mir-s3-cdn-cf.behance.net/project_modules') > -1 ||
           src.indexOf('mir-s3-cdn-cf.behance.net/projects/') > -1 ||
           src.indexOf('mir-cdn.behance.net/project_modules') > -1 ||
           src.indexOf('mir-cdn.behance.net/v1/project_modules') > -1 ||
           // Also: any subdomain.behance.net with project_modules path
           (src.indexOf('.behance.net') > -1 && src.indexOf('project_modules') > -1) ||
           // Also accept images inside an EditProject context (more permissive)
           (location.pathname.indexOf('/edit') > -1 && src.indexOf('behance.net') > -1 && src.indexOf('project_modules') > -1);
  }}

  function extractContent(){{
    setMsg('🔍 جاري استخراج المحتوى...', '');

    // Final capture before extraction
    captureImagesNow();

    var allItems = [];
    var seen = {{}};

    var title = '';
    var ogT = document.querySelector('meta[property="og:title"]');
    if(ogT) title = ogT.content;
    if(!title) title = (document.title||'').split('::')[0].split('|')[0].trim();

    var desc = '';
    var ogD = document.querySelector('meta[property="og:description"]');
    if(ogD) desc = ogD.content;

    var cover = '';
    var ogI = document.querySelector('meta[property="og:image"]');
    if(ogI) cover = ogI.content;

    // 1. All cached images (from <img> tags during scroll)
    for(var key in imageCache){{
      if(seen[key]) continue;
      seen[key] = 1;
      var ic = imageCache[key];
      allItems.push({{
        type:'image', src: ic.src,
        y: ic.y, x: ic.x, width: ic.width, height: ic.height
      }});
    }}

    // 2. All cached background-image elements
    for(var key in bgCache){{
      if(seen[key]) continue;
      seen[key] = 1;
      var bc = bgCache[key];
      allItems.push({{
        type:'image', src: bc.src,
        y: bc.y, x: bc.x, width: bc.width, height: bc.height
      }});
    }}

    // 3. Videos
    var allVids = document.querySelectorAll('video');
    for(var i=0; i<allVids.length; i++){{
      var v = allVids[i].currentSrc || allVids[i].src || '';
      if(v && v.indexOf('http')===0 && !seen[v]){{
        seen[v]=1;
        var rect = allVids[i].getBoundingClientRect();
        allItems.push({{type:'video', src: v, y: rect.top + window.scrollY, x: rect.left, width: rect.width, height: rect.height}});
      }}
    }}

    // 4. Iframes (Vimeo / YouTube)
    var allFrames = document.querySelectorAll('iframe');
    for(var i=0; i<allFrames.length; i++){{
      var f = allFrames[i].src || '';
      if(f && (f.indexOf('vimeo.com')>-1 || f.indexOf('youtube.com')>-1) && !seen[f]){{
        seen[f]=1;
        var rect = allFrames[i].getBoundingClientRect();
        allItems.push({{type:'embed', url: f, y: rect.top + window.scrollY, x: rect.left, width: rect.width, height: rect.height}});
      }}
    }}

    // 5. Text blocks
    var textNodes = document.querySelectorAll('p, h1, h2, h3, blockquote');
    for(var i=0; i<textNodes.length; i++){{
      var node = textNodes[i];
      var text = (node.innerText||'').trim();
      if(text.length < 30 || text.length > 4000) continue;
      if(node.closest('nav, header, footer, [class*="toolbar"], [class*="appreciation"], [class*="comment"], [class*="related"], [class*="profile-stats"], [class*="byline"]')) continue;
      var key = 't:'+text.slice(0,50);
      if(seen[key]) continue;
      seen[key] = 1;
      var rect = node.getBoundingClientRect();
      allItems.push({{type:'text', content: text, y: rect.top + window.scrollY, x: rect.left, width: rect.width, height: rect.height}});
    }}

    // Sort by Y position (document order)
    allItems.sort(function(a,b){{
      var dy = (a.y||0) - (b.y||0);
      if(Math.abs(dy) < 20) return (a.x||0) - (b.x||0);  // same row → left-to-right
      return dy;
    }});

    // Group images that are on the same row (within 30px Y) → image_row
    var modules = [];
    var i = 0;
    while(i < allItems.length){{
      var item = allItems[i];
      if(item.type !== 'image'){{
        modules.push(stripMeta(item));
        i++;
        continue;
      }}
      // Check if next item(s) are images on the same row
      var rowItems = [item];
      var j = i + 1;
      while(j < allItems.length && allItems[j].type === 'image' && Math.abs(allItems[j].y - item.y) < 30){{
        rowItems.push(allItems[j]);
        j++;
      }}
      if(rowItems.length >= 2){{
        // It's a grid row
        modules.push({{type:'image_row', images: rowItems.map(function(r){{ return r.src; }})}});
      }} else {{
        modules.push(stripMeta(item));
      }}
      i = j;
    }}

    function stripMeta(it){{
      var c = {{}};
      for(var k in it){{ if(k!=='y' && k!=='x' && k!=='width' && k!=='height' && k!=='el') c[k] = it[k]; }}
      return c;
    }}

    if(!modules.length){{
      removeOverlay();
      alert('⚠️ لم يتم العثور على محتوى\\n\\nتأكد إنك على صفحة مشروع Behance (وليس صفحة البروفايل)');
      return;
    }}

    var totalImages = 0;
    var totalEmbeds = 0;
    var totalText = 0;
    modules.forEach(function(m){{
      if(m.type === 'image') totalImages++;
      else if(m.type === 'image_row') totalImages += m.images.length;
      else if(m.type === 'embed') totalEmbeds++;
      else if(m.type === 'text') totalText++;
    }});

    console.log('[Bookmarklet] Extracted:', {{
      images: totalImages, embeds: totalEmbeds, text: totalText,
      imageCache: Object.keys(imageCache).length,
      bgCache: Object.keys(bgCache).length,
      modules: modules.length
    }});

    // Convert images to base64 IN BROWSER (Behance returns 403 to server but works in browser)
    setMsg('🖼️ جاري تحويل الصور...', '0 / ' + totalImages);

    function urlToBase64(url){{
      return new Promise(function(resolve){{
        var img = new Image();
        img.crossOrigin = 'anonymous';
        var done = false;
        var timeoutId = setTimeout(function(){{
          if(done) return;
          done = true;
          // Try fetch() as fallback
          fetch(url, {{credentials:'include'}})
            .then(function(r){{ if(!r.ok) throw new Error('fail'); return r.blob(); }})
            .then(function(blob){{
              var reader = new FileReader();
              reader.onload = function(){{ resolve(reader.result); }};
              reader.onerror = function(){{ resolve(null); }};
              reader.readAsDataURL(blob);
            }})
            .catch(function(){{ resolve(null); }});
        }}, 8000);
        img.onload = function(){{
          if(done) return;
          done = true;
          clearTimeout(timeoutId);
          try {{
            var canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth || 1200;
            canvas.height = img.naturalHeight || 800;
            var ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            // Use JPEG with 0.9 quality for smaller payload
            var dataUrl = canvas.toDataURL('image/jpeg', 0.9);
            if(dataUrl.length < 300) {{ resolve(null); return; }}
            resolve(dataUrl);
          }} catch(e){{
            // CORS taint — fallback to fetch
            fetch(url, {{credentials:'include'}})
              .then(function(r){{ if(!r.ok) throw new Error('fail'); return r.blob(); }})
              .then(function(blob){{
                var reader = new FileReader();
                reader.onload = function(){{ resolve(reader.result); }};
                reader.onerror = function(){{ resolve(null); }};
                reader.readAsDataURL(blob);
              }})
              .catch(function(){{ resolve(null); }});
          }}
        }};
        img.onerror = function(){{
          if(done) return;
          done = true;
          clearTimeout(timeoutId);
          // Fallback to fetch
          fetch(url, {{credentials:'include'}})
            .then(function(r){{ if(!r.ok) throw new Error('fail'); return r.blob(); }})
            .then(function(blob){{
              var reader = new FileReader();
              reader.onload = function(){{ resolve(reader.result); }};
              reader.onerror = function(){{ resolve(null); }};
              reader.readAsDataURL(blob);
            }})
            .catch(function(){{ resolve(null); }});
        }};
        img.src = url;
      }});
    }}

    // Process all image URLs in parallel (with concurrency limit)
    async function convertAllImages(){{
      var allUrls = [];
      modules.forEach(function(m){{
        if(m.type === 'image') allUrls.push(m.src);
        else if(m.type === 'image_row') (m.images||[]).forEach(function(s){{ allUrls.push(s); }});
      }});

      var urlToData = {{}};
      var done = 0;
      var concurrency = 4;
      var idx = 0;

      async function worker(){{
        while(idx < allUrls.length){{
          var myIdx = idx++;
          var url = allUrls[myIdx];
          if(urlToData[url] !== undefined){{ done++; continue; }}
          var data = await urlToBase64(url);
          urlToData[url] = data;
          done++;
          setMsg('🖼️ جاري تحويل الصور...', done + ' / ' + allUrls.length);
        }}
      }}

      var workers = [];
      for(var w=0; w<concurrency; w++) workers.push(worker());
      await Promise.all(workers);

      // Replace URLs with base64 (only successful ones)
      var newModules = [];
      modules.forEach(function(m){{
        if(m.type === 'image'){{
          var data = urlToData[m.src];
          if(data) newModules.push({{type:'image', src: data, originalUrl: m.src}});
          else newModules.push({{type:'image', src: m.src}});  // keep URL as fallback
        }} else if(m.type === 'image_row'){{
          var newImages = [];
          (m.images||[]).forEach(function(s){{
            var data = urlToData[s];
            newImages.push(data || s);
          }});
          if(newImages.length) newModules.push({{type:'image_row', images: newImages}});
        }} else {{
          newModules.push(m);
        }}
      }});

      var successCount = 0;
      Object.keys(urlToData).forEach(function(k){{ if(urlToData[k]) successCount++; }});
      console.log('[Bookmarklet] Converted', successCount, '/', allUrls.length, 'images to base64');

      return newModules;
    }}

    convertAllImages().then(function(processedModules){{
      setMsg('📤 جاري الإرسال...', 'لا تغلق الصفحة');
      sendToServer(processedModules);
    }});

    function sendToServer(processedModules){{
      fetch('{base}/api/bookmarklet/submit', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        title: title, description: desc, cover: cover, modules: processedModules,
        source_url: location.href
      }})
    }})
    .then(function(r){{
      if(!r.ok) throw new Error('Server returned ' + r.status);
      return r.json();
    }})
    .then(function(d){{
      removeOverlay();
      if(d.import_id){{
        var url = '{base}/admin?bh=' + encodeURIComponent(d.import_id);
        var ok = confirm('✅ تم استخراج ' + d.count + ' عنصر بنجاح!\\n\\nاضغط OK لفتح لوحة التحكم');
        if(ok){{
          // Use window.open for Safari compatibility (avoids "string did not match" error)
          var w = window.open(url, '_blank');
          if(!w){{
            // Popup blocked → fallback
            location.href = url;
          }}
        }}
      }} else {{
        alert('❌ ' + (d.error||'فشل الإرسال'));
      }}
    }})
    .catch(function(e){{
      removeOverlay();
      alert('❌ خطأ في الإرسال:\\n' + e.message + '\\n\\nتأكد من أنك مسجل دخول في موقع Portfolio');
    }});
    }}
  }}
}})();'''
    return js, 200, {'Content-Type':'application/javascript; charset=utf-8',
                     'Cache-Control':'no-cache',
                     'Access-Control-Allow-Origin':'*'}


@app.route('/api/bookmarklet/submit', methods=['POST', 'OPTIONS'])
def bookmarklet_submit():
    """Receives scraped data from bookmarklet running on Behance."""
    if request.method == 'OPTIONS':
        resp = jsonify({'ok':True})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    d = request.get_json() or {}
    # Sanitize modules
    raw_mods = d.get('modules') or []
    modules = []
    for m in raw_mods[:80]:
        if not isinstance(m, dict): continue
        t = m.get('type')
        if t == 'image':
            src = (m.get('src') or '')[:1000]
            if src.startswith('http'): modules.append({'type':'image','src':src})
        elif t == 'image_row':
            imgs = m.get('images') or []
            valid = []
            for img_src in imgs[:6]:
                s = (img_src or '')[:1000] if isinstance(img_src, str) else ''
                if s.startswith('http'): valid.append(s)
            if len(valid) >= 2:
                modules.append({'type':'image_row','images':valid})
            elif len(valid) == 1:
                modules.append({'type':'image','src':valid[0]})
        elif t == 'video':
            src = (m.get('src') or '')[:1000]
            if src.startswith('http'): modules.append({'type':'video','src':src})
        elif t == 'embed':
            url = (m.get('url') or '')[:500]
            if url.startswith('http'): modules.append({'type':'embed','url':url})
        elif t == 'text':
            content = (m.get('content') or '')[:5000]
            if content.strip(): modules.append({'type':'text','content':content})

    if not modules:
        resp = jsonify({'error':'لا توجد عناصر صالحة'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 400

    # Generate short import ID
    import_id = base64.urlsafe_b64encode(os.urandom(9)).decode().rstrip('=')

    _pending_imports[import_id] = {
        'data': {
            'title': (d.get('title') or '')[:300],
            'description': (d.get('description') or '')[:2000],
            'cover': (d.get('cover') or '')[:500],
            'modules': modules,
            'source_url': (d.get('source_url') or '')[:500],
        },
        'expires_at': time.time() + 1800,  # 30 minutes
    }
    # Cleanup expired
    now = time.time()
    expired = [k for k,v in _pending_imports.items() if v['expires_at'] < now]
    for k in expired: _pending_imports.pop(k, None)

    resp = jsonify({'ok':True, 'import_id': import_id, 'count': len(modules)})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/api/bookmarklet/get/<import_id>')
@login_required
def bookmarklet_get(import_id):
    """Admin fetches the pending import data."""
    item = _pending_imports.get(import_id)
    if not item: return jsonify({'error':'لم يتم العثور على البيانات (قد تكون انتهت صلاحيتها)'}), 404
    if item['expires_at'] < time.time():
        _pending_imports.pop(import_id, None)
        return jsonify({'error':'انتهت صلاحية البيانات'}), 410
    # One-shot retrieval
    _pending_imports.pop(import_id, None)
    return jsonify({'ok':True, 'data': item['data']})



# ══════════════ CLIENT LOGOS ══════════════

@app.route('/api/users/by-username/<username>', methods=['GET'])
def get_user_by_username(username):
    """Public — get user_id from username (used by testimonial form)."""
    db = get_db()
    row = db.execute("SELECT id, username FROM users WHERE username=?", (username,)).fetchone()
    if not row: return jsonify({'error':'not found'}), 404
    return jsonify({'id': row['id'], 'username': row['username']})

@app.route('/api/logos', methods=['GET'])
def list_logos():
    """Public endpoint — returns logos for given user_id (or current user)."""
    user_id = request.args.get('user_id', type=int) or session.get("user_id")
    if not user_id: return jsonify({'logos': []})
    db = get_db()
    rows = db.execute(
        "SELECT id, name, logo_url, website_url, sort_order FROM client_logos WHERE user_id=? ORDER BY sort_order, id",
        (user_id,)
    ).fetchall()
    return jsonify({'logos': [dict(r) for r in rows]})

@app.route('/api/logos', methods=['POST'])
@login_required
def create_logo():
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()[:100]
    logo_data = d.get('logo') or ''
    website = (d.get('website_url') or '').strip()[:500]
    if not logo_data:
        return jsonify({'error':'لم يتم رفع الشعار'}), 400

    user_id = uid()
    logo_url = ''
    if logo_data.startswith('data:'):
        logo_url = save_dataurl(logo_data, ALLOWED_IMG, user_id)
        if logo_url == '__STORAGE_LIMIT__':
            return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
    elif logo_data.startswith('/uploads/'):
        logo_url = logo_data
    else:
        return jsonify({'error':'صيغة غير صالحة'}), 400

    db = get_db()
    sort_order = (db.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM client_logos WHERE user_id=?", (user_id,)
    ).fetchone()[0] or 0) + 1
    cur = db.execute(
        "INSERT INTO client_logos(user_id,name,logo_url,website_url,sort_order) VALUES(?,?,?,?,?)",
        (user_id, name, logo_url, website, sort_order)
    )
    db.commit()
    return jsonify({'ok':True,'id':cur.lastrowid,'logo_url':logo_url})

@app.route('/api/logos/<int:lid>', methods=['PUT'])
@login_required
def update_logo(lid):
    d = request.get_json() or {}
    db = get_db()
    row = db.execute("SELECT user_id, logo_url FROM client_logos WHERE id=?", (lid,)).fetchone()
    if not row or row['user_id'] != uid():
        return jsonify({'error':'غير موجود'}), 404
    name = (d.get('name') or '').strip()[:100]
    website = (d.get('website_url') or '').strip()[:500]
    new_logo_url = row['logo_url']
    if d.get('logo'):
        ld = d['logo']
        if ld.startswith('data:'):
            saved = save_dataurl(ld, ALLOWED_IMG, uid())
            if saved == '__STORAGE_LIMIT__':
                return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
            # Delete old
            try: delete_file(row['logo_url'])
            except: pass
            new_logo_url = saved
    db.execute(
        "UPDATE client_logos SET name=?, website_url=?, logo_url=? WHERE id=?",
        (name, website, new_logo_url, lid)
    )
    db.commit()
    return jsonify({'ok':True,'logo_url':new_logo_url})

@app.route('/api/logos/<int:lid>', methods=['DELETE'])
@login_required
def delete_logo(lid):
    db = get_db()
    row = db.execute("SELECT user_id, logo_url FROM client_logos WHERE id=?", (lid,)).fetchone()
    if not row or row['user_id'] != uid():
        return jsonify({'error':'غير موجود'}), 404
    try: delete_file(row['logo_url'])
    except: pass
    db.execute("DELETE FROM client_logos WHERE id=?", (lid,))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/logos/reorder', methods=['PUT'])
@login_required
def reorder_logos():
    d = request.get_json() or {}
    ids = d.get('order', [])
    db = get_db()
    for i, lid in enumerate(ids):
        db.execute("UPDATE client_logos SET sort_order=? WHERE id=? AND user_id=?", (i, lid, uid()))
    db.commit()
    return jsonify({'ok':True})


# ══════════════ TESTIMONIALS ══════════════

@app.route('/api/testimonials', methods=['GET'])
def list_testimonials():
    """Public — returns approved testimonials for given user."""
    user_id = request.args.get('user_id', type=int) or session.get("user_id")
    if not user_id: return jsonify({'testimonials': []})
    # If owner is asking from admin, show all
    show_all = session.get("user_id") == user_id and request.args.get('all') == '1'
    db = get_db()
    if show_all:
        rows = db.execute(
            "SELECT id, name, role, company, content, avatar_url, rating, source, approved, sort_order, created_at "
            "FROM testimonials WHERE user_id=? ORDER BY sort_order, id DESC",
            (user_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, name, role, company, content, avatar_url, rating, sort_order "
            "FROM testimonials WHERE user_id=? AND approved=1 ORDER BY sort_order, id DESC",
            (user_id,)
        ).fetchall()
    return jsonify({'testimonials': [dict(r) for r in rows]})

@app.route('/api/testimonials', methods=['POST'])
@login_required
def create_testimonial():
    """Admin/owner adds a testimonial directly (auto-approved)."""
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()[:100]
    content = (d.get('content') or '').strip()[:2000]
    if not name or not content:
        return jsonify({'error':'الاسم والمحتوى مطلوبان'}), 400

    user_id = uid()
    avatar_url = ''
    avatar_data = d.get('avatar') or ''
    if avatar_data.startswith('data:'):
        avatar_url = save_dataurl(avatar_data, ALLOWED_IMG, user_id)
        if avatar_url == '__STORAGE_LIMIT__':
            return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
    elif avatar_data.startswith('/uploads/'):
        avatar_url = avatar_data

    db = get_db()
    sort_order = (db.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM testimonials WHERE user_id=?", (user_id,)
    ).fetchone()[0] or 0) + 1
    rating = int(d.get('rating', 5))
    rating = max(1, min(5, rating))
    cur = db.execute(
        "INSERT INTO testimonials(user_id,name,role,company,content,avatar_url,rating,source,approved,sort_order) "
        "VALUES(?,?,?,?,?,?,?,?,1,?)",
        (user_id, name, (d.get('role') or '').strip()[:100], (d.get('company') or '').strip()[:100],
         content, avatar_url, rating, 'admin', sort_order)
    )
    db.commit()
    return jsonify({'ok':True,'id':cur.lastrowid})

@app.route('/api/testimonials/submit', methods=['POST'])
def submit_testimonial():
    """Public form — clients/visitors submit testimonials. Goes to pending until owner approves."""
    d = request.get_json() or {}
    user_id = d.get('user_id')
    if not user_id: return jsonify({'error':'مستخدم غير محدد'}), 400
    try: user_id = int(user_id)
    except: return jsonify({'error':'مستخدم غير صالح'}), 400

    db = get_db()
    # testimonials submissions are always open — owner moderates via admin panel

    name = (d.get('name') or '').strip()[:100]
    content = (d.get('content') or '').strip()[:2000]
    if not name or len(content) < 10:
        return jsonify({'error':'الاسم والرأي مطلوبان (الرأي 10 أحرف على الأقل)'}), 400

    role = (d.get('role') or '').strip()[:100]
    company = (d.get('company') or '').strip()[:100]
    rating = int(d.get('rating', 5))
    rating = max(1, min(5, rating))

    # Optional photo upload
    avatar_url = ''
    photo_data = (d.get('photo') or '').strip()
    if photo_data and photo_data.startswith('data:image'):
        saved = save_dataurl(photo_data, ALLOWED_IMG, user_id)
        if saved and saved != '__STORAGE_LIMIT__':
            avatar_url = saved

    sort_order = (db.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM testimonials WHERE user_id=?", (user_id,)
    ).fetchone()[0] or 0) + 1
    db.execute(
        "INSERT INTO testimonials(user_id,name,role,company,content,rating,source,approved,sort_order,avatar_url) "
        "VALUES(?,?,?,?,?,?,?,0,?,?)",
        (user_id, name, role, company, content, rating, 'public', sort_order, avatar_url)
    )
    db.commit()

    # Build portfolio URL for thank-you button
    site_row = db.execute(
        "SELECT value FROM settings WHERE user_id=? AND key='portfolio_site_url'", (user_id,)
    ).fetchone()
    portfolio_url = (site_row['value'].strip() if site_row and site_row['value'] else '')
    if not portfolio_url:
        user_row = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if user_row:
            scheme = 'https' if request.is_secure else 'http'
            portfolio_url = f"{scheme}://{request.host}/u/{user_row['username']}"

    return jsonify({'ok': True, 'portfolio_url': portfolio_url})

@app.route('/api/achievements', methods=['GET'])
@login_required
def get_achievements():
    db = get_db()
    rows = db.execute(
        "SELECT id, icon_url, title, title_en, value, sort_order FROM achievements WHERE user_id=? ORDER BY sort_order, id",
        (uid(),)
    ).fetchall()
    return jsonify({'achievements': [dict(r) for r in rows]})

@app.route('/api/achievements', methods=['POST'])
@login_required
def add_achievement():
    d = request.get_json() or {}
    title = (d.get('title') or '').strip()[:100]
    title_en = (d.get('title_en') or '').strip()[:100]
    value = (d.get('value') or '0').strip()[:50]
    icon_url = ''
    if d.get('icon'):
        saved = save_dataurl(d['icon'], ALLOWED_IMG, uid())
        if saved and saved != '__STORAGE_LIMIT__':
            icon_url = saved
    db = get_db()
    sort_order = (db.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM achievements WHERE user_id=?", (uid(),)
    ).fetchone()[0] or 0) + 1
    cur = db.execute(
        "INSERT INTO achievements(user_id, icon_url, title, title_en, value, sort_order) VALUES(?,?,?,?,?,?)",
        (uid(), icon_url, title, title_en, value, sort_order)
    )
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid, 'icon_url': icon_url})

@app.route('/api/achievements/<int:aid>', methods=['PUT'])
@login_required
def update_achievement(aid):
    d = request.get_json() or {}
    db = get_db()
    row = db.execute("SELECT user_id, icon_url FROM achievements WHERE id=?", (aid,)).fetchone()
    if not row or row['user_id'] != uid(): return jsonify({'error': 'غير موجود'}), 404
    title = (d.get('title') or '').strip()[:100]
    title_en = (d.get('title_en') or '').strip()[:100]
    value = (d.get('value') or '0').strip()[:50]
    icon_url = row['icon_url']
    if d.get('icon'):
        saved = save_dataurl(d['icon'], ALLOWED_IMG, uid())
        if saved and saved != '__STORAGE_LIMIT__':
            delete_file(icon_url, uid())
            icon_url = saved
    elif 'icon' in d and d['icon'] == '':
        delete_file(icon_url, uid())
        icon_url = ''
    db.execute(
        "UPDATE achievements SET title=?, title_en=?, value=?, icon_url=? WHERE id=? AND user_id=?",
        (title, title_en, value, icon_url, aid, uid())
    )
    db.commit()
    return jsonify({'ok': True, 'icon_url': icon_url})

@app.route('/api/achievements/<int:aid>', methods=['DELETE'])
@login_required
def delete_achievement(aid):
    db = get_db()
    row = db.execute("SELECT user_id, icon_url FROM achievements WHERE id=?", (aid,)).fetchone()
    if not row or row['user_id'] != uid(): return jsonify({'error': 'غير موجود'}), 404
    delete_file(row['icon_url'], uid())
    db.execute("DELETE FROM achievements WHERE id=? AND user_id=?", (aid, uid()))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/achievements/public', methods=['GET'])
def get_achievements_public():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({'achievements': []})
    try: user_id = int(user_id)
    except: return jsonify({'achievements': []})
    db = get_db()
    rows = db.execute(
        "SELECT icon_url, title, title_en, value FROM achievements WHERE user_id=? ORDER BY sort_order, id",
        (user_id,)
    ).fetchall()
    return jsonify({'achievements': [dict(r) for r in rows]})

@app.route('/api/testimonials/<int:tid>', methods=['PUT'])
@login_required
def update_testimonial(tid):
    d = request.get_json() or {}
    db = get_db()
    row = db.execute("SELECT user_id, avatar_url FROM testimonials WHERE id=?", (tid,)).fetchone()
    if not row or row['user_id'] != uid():
        return jsonify({'error':'غير موجود'}), 404
    fields, vals = [], []
    for f in ('name','role','company','content'):
        if f in d:
            fields.append(f'{f}=?'); vals.append((d[f] or '').strip()[:2000 if f=='content' else 100])
    if 'rating' in d:
        try:
            r = max(1, min(5, int(d['rating'])))
            fields.append('rating=?'); vals.append(r)
        except: pass
    if 'approved' in d:
        fields.append('approved=?'); vals.append(1 if d['approved'] else 0)
    if d.get('avatar'):
        ad = d['avatar']
        if ad.startswith('data:'):
            saved = save_dataurl(ad, ALLOWED_IMG, uid())
            if saved == '__STORAGE_LIMIT__':
                return jsonify({'error':'⚠️ وصلت للحد الأقصى من المساحة'}), 400
            try: delete_file(row['avatar_url'])
            except: pass
            fields.append('avatar_url=?'); vals.append(saved)
    if fields:
        vals.append(tid)
        db.execute(f"UPDATE testimonials SET {','.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({'ok':True})

@app.route('/api/testimonials/<int:tid>', methods=['DELETE'])
@login_required
def delete_testimonial(tid):
    db = get_db()
    row = db.execute("SELECT user_id, avatar_url FROM testimonials WHERE id=?", (tid,)).fetchone()
    if not row or row['user_id'] != uid():
        return jsonify({'error':'غير موجود'}), 404
    try: delete_file(row['avatar_url'])
    except: pass
    db.execute("DELETE FROM testimonials WHERE id=?", (tid,))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/testimonials/reorder', methods=['PUT'])
@login_required
def reorder_testimonials():
    d = request.get_json() or {}
    ids = d.get('order', [])
    db = get_db()
    for i, tid in enumerate(ids):
        db.execute("UPDATE testimonials SET sort_order=? WHERE id=? AND user_id=?", (i, tid, uid()))
    db.commit()
    return jsonify({'ok':True})

# Public testimonial form page — always accessible
@app.route('/testimonial/<username>')
def testimonial_form_page(username):
    """Public form for clients to submit testimonials."""
    db = get_db()
    user = db.execute("SELECT id, username FROM users WHERE username=?", (username,)).fetchone()
    if not user: abort(404)
    return send_from_directory(app.static_folder, 'testimonial.html')


# ── CONTACT ──
_crate = {}
@app.route('/api/contact', methods=['POST'])
def contact_send():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'x').split(',')[0].strip()
    now = time.time()
    _crate.setdefault(ip, [])
    _crate[ip] = [t for t in _crate[ip] if now-t < 3600]
    if len(_crate[ip]) >= 3: return jsonify({'error':'تم تجاوز الحد المسموح.'}), 429
    d = request.get_json() or {}
    name = (d.get('name') or '').strip()[:100]
    email = (d.get('email') or '').strip()[:200]
    subject = (d.get('subject') or '').strip()[:200]
    message = (d.get('message') or '').strip()[:5000]
    if not name or not email or not message: return jsonify({'error':'الاسم والإيميل والرسالة مطلوبة'}), 400
    if '@' not in email or '.' not in email.split('@')[-1]: return jsonify({'error':'البريد الإلكتروني غير صحيح'}), 400
    api_key = os.environ.get('RESEND_API_KEY',''); to_email = os.environ.get('CONTACT_EMAIL','')
    if not api_key or not to_email: return jsonify({'error':'خدمة الإيميل غير مهيأة'}), 500
    def esc(s): return html_mod.escape(s).replace('\n','<br>')
    subj = subject or f'رسالة جديدة من {name}'
    html_body = f'<div style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5;"><div style="background:#fff;padding:24px;border-radius:8px;border-top:4px solid #ff6b35;"><h2 style="color:#ff6b35;margin-top:0;">📬 رسالة جديدة</h2><p><b>الاسم:</b> {esc(name)}</p><p><b>الإيميل:</b> {esc(email)}</p><p><b>الرسالة:</b><br>{esc(message)}</p></div></div>'
    try:
        req = urllib.request.Request('https://api.resend.com/emails', data=json.dumps({'from':'Portfolio <onboarding@resend.dev>','to':[to_email],'reply_to':email,'subject':subj,'html':html_body}).encode(),
            headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json','User-Agent':'Mozilla/5.0'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
            if result.get('id'): _crate[ip].append(now); return jsonify({'ok':True})
            return jsonify({'error':'فشل الإرسال'}), 500
    except Exception as e: print(f'Contact error: {e}'); return jsonify({'error':'حدث خطأ'}), 500

# ── USER PORTFOLIO ROUTING ──
@app.route('/api/resolve-user')
def resolve_user():
    username = request.args.get('username','').strip()
    host = request.args.get('host','').strip().lower().split(':')[0]
    db = get_db()
    if username:
        user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if user: return jsonify({'user_id':user['id']})
        return jsonify({'error':'not found'}), 404
    if host:
        domain = db.execute("SELECT user_id FROM domains WHERE domain=?", (host,)).fetchone()
        if domain: return jsonify({'user_id':domain['user_id']})
    owner = db.execute("SELECT id FROM users WHERE is_owner=1").fetchone()
    return jsonify({'user_id': owner['id'] if owner else 1})

# ── STATIC ROUTES ──

# ── DATABASE BACKUP (protected) ──
# Download a full copy of the database. Protected by a secret key.
# Usage: https://yoursite.onrender.com/api/db-backup?key=YOUR_SECRET
# The secret comes from the BACKUP_KEY env var (set it in Render dashboard).
@app.route('/api/db-backup')
def db_backup_download():
    secret = os.environ.get('BACKUP_KEY', '')
    given  = request.args.get('key', '')
    # Require a non-empty secret AND an exact match
    if not secret or given != secret:
        return jsonify({'error': 'Unauthorized'}), 403
    if not os.path.exists(DB_PATH):
        return jsonify({'error': 'Database not found'}), 404
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(DB_PATH, as_attachment=True,
                     download_name=f'portfolio_backup_{stamp}.db',
                     mimetype='application/octet-stream')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    r = send_from_directory(UPLOAD_DIR, filename)
    r.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return r

@app.route('/admin')
@app.route('/admin.html')
def admin_page():
    return send_from_directory(app.static_folder, 'admin.html')

@app.route('/owner')
@app.route('/owner.html')
def owner_page():
    return send_from_directory(app.static_folder, 'owner.html')

@app.route('/admin/editor/<int:pid>')
def editor_page(pid):
    if not session.get('logged_in'): return redirect('/admin')
    return send_from_directory(app.static_folder, 'editor.html')

@app.route('/u/<username>')
@app.route('/u/<username>/')
def user_portfolio(username):
    if 'text/markdown' in request.headers.get('Accept', ''):
        md = _portfolio_markdown(username)
        if md:
            return Response(md, mimetype='text/markdown; charset=utf-8',
                            headers={'x-markdown-tokens': 'true'})
        return Response("# Not Found\n\nUser not found.", status=404, mimetype='text/markdown')
    return send_from_directory(app.static_folder, 'index.html')

# ── AGENT-READY ENDPOINTS ──

@app.route('/llms.txt')
def llms_txt():
    db = get_db()
    host = request.host_url.rstrip('/')
    users = db.execute(
        "SELECT u.username, s_name.value as name, s_bio.value as bio "
        "FROM users u "
        "LEFT JOIN settings s_name ON s_name.user_id=u.id AND s_name.key='name' "
        "LEFT JOIN settings s_bio  ON s_bio.user_id=u.id  AND s_bio.key='bio' "
        "WHERE u.username IS NOT NULL ORDER BY u.id"
    ).fetchall()
    lines = [
        "# Portfolio Builder — AI Agent Discovery File",
        "# Format: llms.txt v1 (https://llmstxt.org)",
        "",
        "## About",
        "A multi-tenant portfolio builder. Each user has a public portfolio page.",
        "",
        "## Portfolios",
    ]
    for u in users:
        n = u['name'] or u['username']
        b = u['bio'] or ''
        line = f"- [{n}]({host}/u/{u['username']})"
        if b: line += f": {b}"
        lines.append(line)
    lines += [
        "",
        "## API (public, no auth required)",
        f"- Settings:      GET {host}/api/settings?username=<username>",
        f"- Projects:      GET {host}/api/projects?username=<username>",
        f"- Testimonials:  GET {host}/api/testimonials?username=<username>",
        f"- Achievements:  GET {host}/api/achievements/public?user_id=<id>",
        f"- OpenAPI spec:  GET {host}/openapi.json",
    ]
    return Response('\n'.join(lines), mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    db = get_db()
    host = request.host_url.rstrip('/')
    usernames = db.execute("SELECT username FROM users WHERE username IS NOT NULL").fetchall()
    urls = [f'  <url><loc>{host}/u/{u["username"]}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>'
            for u in usernames]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(urls)
        + '\n</urlset>'
    )
    return Response(body, mimetype='application/xml')

@app.route('/openapi.json')
def openapi_spec():
    host = request.host_url.rstrip('/')
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Portfolio Builder API", "version": "1.0.0",
                 "description": "Public API for multi-tenant portfolio builder"},
        "servers": [{"url": host}],
        "paths": {
            "/api/settings": {"get": {"summary": "Get portfolio settings",
                "parameters": [{"name": "username","in": "query","required": True,"schema": {"type": "string"}}],
                "responses": {"200": {"description": "Portfolio settings JSON"}}}},
            "/api/projects": {"get": {"summary": "Get portfolio projects",
                "parameters": [{"name": "username","in": "query","required": True,"schema": {"type": "string"}}],
                "responses": {"200": {"description": "Projects list"}}}},
            "/api/testimonials": {"get": {"summary": "Get approved testimonials",
                "parameters": [{"name": "username","in": "query","required": True,"schema": {"type": "string"}}],
                "responses": {"200": {"description": "Testimonials list"}}}},
            "/api/testimonials/submit": {"post": {"summary": "Submit a testimonial",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "required": ["user_id", "name", "content"],
                    "properties": {
                        "user_id": {"type": "integer"},
                        "name":    {"type": "string"},
                        "content": {"type": "string"},
                        "rating":  {"type": "integer", "minimum": 1, "maximum": 5},
                        "role":    {"type": "string"},
                        "company": {"type": "string"},
                        "photo":   {"type": "string", "description": "Base64 data URL"}
                    }
                }}}},
                "responses": {"200": {"description": "ok"}}}},
            "/api/achievements/public": {"get": {"summary": "Get public achievements/stats",
                "parameters": [{"name": "user_id","in": "query","required": True,"schema": {"type": "integer"}}],
                "responses": {"200": {"description": "Achievements list"}}}},
            "/api/health": {"get": {"summary": "Health check",
                "responses": {"200": {"description": "Service status"}}}}
        }
    }
    return Response(json.dumps(spec, ensure_ascii=False), mimetype='application/openapi+json')

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok', 'service': 'portfolio-builder', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/.well-known/api-catalog')
def api_catalog():
    host = request.host_url.rstrip('/')
    catalog = {"linkset": [{"anchor": f"{host}/api/",
        "service-desc": [{"href": f"{host}/openapi.json", "type": "application/openapi+json"}],
        "service-doc":  [{"href": f"{host}/llms.txt",    "type": "text/plain"}],
        "status":       [{"href": f"{host}/api/health",  "type": "application/json"}]
    }]}
    return Response(json.dumps(catalog), mimetype='application/linkset+json')

@app.route('/.well-known/mcp/server-card.json')
def mcp_server_card():
    host = request.host_url.rstrip('/')
    return jsonify({
        "serverInfo": {"name": "Portfolio Builder", "version": "1.0.0"},
        "transport":  {"type": "http", "url": f"{host}/api/"},
        "capabilities": {
            "portfolios":   {"description": "Fetch portfolio data by username"},
            "projects":     {"description": "Fetch portfolio projects"},
            "testimonials": {"description": "Submit & fetch testimonials"},
            "achievements": {"description": "Fetch public stats & achievements"}
        }
    })

@app.route('/.well-known/agent-skills/index.json')
def agent_skills_index():
    host = request.host_url.rstrip('/')
    return jsonify({
        "$schema": "https://agentskills.io/schema/v0.2.0/index.json",
        "skills": [
            {"name": "get-portfolio", "type": "api",
             "description": "Get a user portfolio (settings, projects, testimonials)",
             "url": f"{host}/api/settings?username={{username}}"},
            {"name": "submit-testimonial", "type": "api",
             "description": "Submit a testimonial for a portfolio owner",
             "url": f"{host}/api/testimonials/submit"}
        ]
    })

@app.route('/.well-known/oauth-protected-resource')
def oauth_protected_resource():
    host = request.host_url.rstrip('/')
    return jsonify({
        "resource":                 f"{host}/api/",
        "authorization_servers":    [],
        "scopes_supported":         ["read:portfolio", "write:testimonial"],
        "bearer_methods_supported": ["header"]
    })

@app.route('/.well-known/oauth-authorization-server')
@app.route('/.well-known/openid-configuration')
def oauth_discovery():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414) — read-only public API."""
    host = request.host_url.rstrip('/')
    return jsonify({
        "issuer":                               host,
        "authorization_endpoint":              f"{host}/api/auth/authorize",
        "token_endpoint":                      f"{host}/api/auth/token",
        "jwks_uri":                            f"{host}/.well-known/jwks.json",
        "response_types_supported":            ["token"],
        "grant_types_supported":               ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported":                    ["read:portfolio", "write:testimonial"]
    })

@app.after_request
def add_agent_link_headers(response):
    """Inject Link headers on portfolio pages for agent discovery (RFC 8288)."""
    if request.path in ('', '/') or request.path.startswith('/u/'):
        host = request.host_url.rstrip('/')
        response.headers['Link'] = (
            f'<{host}/.well-known/api-catalog>; rel="api-catalog", '
            f'<{host}/openapi.json>; rel="service-desc"; type="application/openapi+json", '
            f'<{host}/llms.txt>; rel="describedby"; type="text/plain", '
            f'<{host}/sitemap.xml>; rel="sitemap", '
            f'<{host}/.well-known/mcp/server-card.json>; rel="mcp-server-card"'
        )
    return response

def _portfolio_markdown(username):
    """Shared helper: build markdown for a portfolio username."""
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        return None
    rows = db.execute("SELECT key, value FROM settings WHERE user_id=?", (user['id'],)).fetchall()
    stg  = {r['key']: r['value'] for r in rows}
    try: ct = json.loads(stg.get('content', '{}'))
    except: ct = {}
    hero  = ct.get('hero', {})
    about = ct.get('about', {})
    name  = hero.get('name_ar') or hero.get('name_en') or username
    role  = hero.get('role_ar') or hero.get('role_en') or ''
    bio   = about.get('bio_ar') or about.get('bio_en') or ''
    skills = ct.get('skills', {}).get('items', [])
    md  = f"# {name}\n\n"
    if role: md += f"**{role}**\n\n"
    if bio:  md += f"{bio}\n\n"
    if skills:
        md += "## Skills\n\n"
        for s in skills:
            sn = s.get('name_ar') or s.get('name_en') or s.get('name') or ''
            if sn: md += f"- {sn}\n"
        md += "\n"
    md += f"[View Portfolio]({request.host_url}u/{username})\n"
    return md

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    # Markdown Negotiation for root (owner portfolio)
    if path == '' and 'text/markdown' in request.headers.get('Accept', ''):
        db   = get_db()
        owner = db.execute("SELECT username FROM users WHERE is_owner=1").fetchone()
        if owner:
            md = _portfolio_markdown(owner['username'])
            if md:
                return Response(md, mimetype='text/markdown; charset=utf-8',
                                headers={'x-markdown-tokens': 'true'})
    full = os.path.join(app.static_folder, path)
    if path and os.path.exists(full): return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'🚀 http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV')=='development')
