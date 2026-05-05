import os, sqlite3, json, secrets, uuid, re, base64, time, shutil, threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from flask import Flask, request, jsonify, session, send_from_directory, abort, redirect
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
    {"id":"hero",       "label_ar":"الرئيسية",  "label_en":"Hero",          "visible":True,"order":0},
    {"id":"about",      "label_ar":"عن النفس",   "label_en":"About",         "visible":True,"order":1},
    {"id":"expertise",  "label_ar":"الخدمات",    "label_en":"Key Expertise", "visible":True,"order":2},
    {"id":"education",  "label_ar":"التعليم",     "label_en":"Education",     "visible":True,"order":3},
    {"id":"skills",     "label_ar":"المهارات",    "label_en":"Skills",        "visible":True,"order":4},
    {"id":"tools",      "label_ar":"الأدوات",     "label_en":"Tools",         "visible":True,"order":5},
    {"id":"experience", "label_ar":"الخبرات",     "label_en":"Experience",    "visible":True,"order":6},
    {"id":"projects",   "label_ar":"المشاريع",    "label_en":"Projects",      "visible":True,"order":7},
    {"id":"contact",    "label_ar":"تواصل معي",   "label_en":"Contact",       "visible":True,"order":8},
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
        ('style_theme', 'default'),
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
                modules      TEXT DEFAULT '[]'
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

        # migrations for projects
        p_cols = [r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()]
        for col, defval in [('user_id','1'),('project_type',"'grid'"),('modules',"'[]'")]:
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
        default_settings(owner_id, db)

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
    total_projects = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    total_storage  = db.execute("SELECT SUM(storage_used_mb) FROM users").fetchone()[0] or 0
    return jsonify({'total_users': total_users, 'total_projects': total_projects, 'total_storage_mb': round(total_storage, 1)})

# ── MY STORAGE (client) ──
@app.route('/api/me/storage')
@login_required
def my_storage():
    user = get_db().execute("SELECT storage_limit_mb, storage_used_mb FROM users WHERE id=?", (uid(),)).fetchone()
    if not user: return jsonify({'error':'not found'}), 404
    return jsonify({'storage_limit_mb':user['storage_limit_mb'],'storage_used_mb':round(user['storage_used_mb'],2),'storage_pct':round(user['storage_used_mb']/user['storage_limit_mb']*100,1) if user['storage_limit_mb'] else 0})

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
    return {'id':row['id'],'title':row['title'],'category':row['category'],'description':row['description'] or '',
            'mediaType':row['media_type'],'coverImage':row['cover_url'],'videoUrl':row['video_url'],
            'images':[r['url'] for r in imgs],'date':row['created_at'][:10],
            'projectType':row['project_type'] or 'grid','modules':mods}

@app.route('/api/projects')
def get_projects():
    user_id = session.get('user_id')
    if not user_id:
        uid_p = request.args.get('user_id')
        if uid_p: user_id = int(uid_p)
        else:
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
    cur = db.execute('INSERT INTO projects(user_id,title,category,description,media_type,cover_url,video_url,project_type) VALUES(?,?,?,?,?,?,?,?)',
        (user_id, title, d.get('category','Social Media'), d.get('description',''), d.get('mediaType','image'), cover_url, video_url, d.get('projectType','grid')))
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
    user_id = uid(); ids = request.get_json().get('ids', [])
    db = get_db()
    for i, pid in enumerate(ids):
        db.execute('UPDATE projects SET sort_order=? WHERE id=? AND user_id=?', (len(ids)-i, pid, user_id))
    db.commit(); return jsonify({'ok':True})

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
    user_id = session.get('user_id')
    if not user_id:
        uid_p = request.args.get('user_id')
        if uid_p: user_id = int(uid_p)
        else:
            owner = get_db().execute("SELECT id FROM users WHERE is_owner=1").fetchone()
            user_id = owner['id'] if owner else 1
    rows = get_db().execute('SELECT key,value FROM settings WHERE user_id=?', (user_id,)).fetchall()
    out = {}
    for r in rows:
        try: out[r['key']] = json.loads(r['value'])
        except: out[r['key']] = r['value']
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
import urllib.request, urllib.error, html as html_mod

def fetch_url(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8','replace'), r.headers.get_content_type()

def proxy_one(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.behance.net/'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        ct = resp.headers.get_content_type() or 'image/jpeg'
        return f'data:{ct};base64,{base64.b64encode(resp.read()).decode()}'

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

@app.route('/api/behance/fetch', methods=['POST'])
@login_required
def behance_fetch():
    url = (request.get_json() or {}).get('url','').strip()
    if 'behance.net' not in url: return jsonify({'error':'يجب أن يكون رابط Behance'}), 400
    try:
        body, _ = fetch_url(url)
        title = ''; t = re.search(r'<meta property="og:title"\s+content="([^"]+)"', body)
        if t: title = html_mod.unescape(t.group(1))
        if not title:
            t2 = re.search(r'<title>([^<]+)</title>', body)
            if t2: title = html_mod.unescape(t2.group(1).split('::')[0].strip())
        desc = ''; dv = re.search(r'<meta property="og:description"\s+content="([^"]+)"', body)
        if dv: desc = html_mod.unescape(dv.group(1))
        cm = re.search(r'<meta property="og:image"\s+content="([^"]+)"', body)
        cover = html_mod.unescape(cm.group(1)) if cm else ''
        img_urls = []
        for mv in re.finditer(r'"url"\s*:\s*"(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"]+)"', body):
            u = mv.group(1)
            if ('fs/' in u or 'max_1200/' in u or 'max_3840/' in u) and u not in img_urls: img_urls.append(u)
        if not img_urls:
            for mv in re.finditer(r'(https://mir-s3-cdn-cf\.behance\.net/project_modules/[^"\s]+\.(?:jpg|png|jpeg|webp))', body):
                u = mv.group(1)
                if u not in img_urls: img_urls.append(u)
        cover_b64 = ''
        if cover:
            try: cover_b64 = proxy_one(cover)
            except: pass
        return jsonify({'title':title,'description':desc,'cover':cover,'cover_b64':cover_b64,'images':img_urls[:20]})
    except Exception as e: return jsonify({'error':str(e)}), 502

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
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def serve(path):
    full = os.path.join(app.static_folder, path)
    if path and os.path.exists(full): return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'🚀 http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV')=='development')
