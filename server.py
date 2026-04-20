import os, sqlite3, json, secrets, uuid, re, base64
from flask import Flask, request, jsonify, session, send_from_directory, abort
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True)

DB_PATH    = os.path.join(os.path.dirname(__file__), 'portfolio.db')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'public', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin123')

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
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                category   TEXT NOT NULL,
                description TEXT DEFAULT '',
                media_type TEXT DEFAULT 'image',
                cover_url  TEXT DEFAULT NULL,
                video_url  TEXT DEFAULT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
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
        ''')
        defaults = [
            ('whatsapp',''),('behance',''),('instagram',''),('linkedin',''),('facebook',''),
            ('photo_url',''),('hero_cover_url',''),('video_cols','4'),
            ('vimeo_token',''),
            ('colors',   DEFAULT_COLORS),
            ('sections', DEFAULT_SECTIONS),
            ('content',  DEFAULT_CONTENT),
        ]
        for k, v in defaults:
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))
        db.commit()

init_db()

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
    d = request.get_json()
    if d.get('username') == ADMIN_USER and d.get('password') == ADMIN_PASS:
        session['logged_in'] = True
        return jsonify({'ok': True})
    return jsonify({'error': 'بيانات غير صحيحة'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear(); return jsonify({'ok': True})

@app.route('/api/auth/check')
def auth_check():
    return jsonify({'logged_in': bool(session.get('logged_in'))})

# ─────────────────────────── FILES ───────────────────────────────────────────
ALLOWED_IMG = {'jpg','jpeg','png','gif','webp'}
ALLOWED_VID = {'mp4','mov','webm','avi'}

def save_dataurl(dataurl, allowed_exts):
    m = re.match(r'data:([^;]+);base64,(.+)', dataurl, re.DOTALL)
    if not m: return None
    mime, b64 = m.group(1), m.group(2)
    ext = {'image/jpeg':'jpg','image/png':'png','image/gif':'gif','image/webp':'webp',
           'video/mp4':'mp4','video/quicktime':'mov','video/webm':'webm','video/avi':'avi'}.get(mime,'bin')
    if ext not in allowed_exts: return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, fname), 'wb') as f:
        f.write(base64.b64decode(b64))
    return f"/uploads/{fname}"

def delete_file(url):
    if url and url.startswith('/uploads/'):
        p = os.path.join(UPLOAD_DIR, os.path.basename(url))
        if os.path.exists(p): os.remove(p)

# ─────────────────────────── PROJECTS ────────────────────────────────────────
def project_to_dict(row, db):
    imgs = db.execute('SELECT url FROM project_images WHERE project_id=? ORDER BY sort_order',(row['id'],)).fetchall()
    return {'id':row['id'],'title':row['title'],'category':row['category'],
            'description':row['description'] or '','mediaType':row['media_type'],
            'coverImage':row['cover_url'],'videoUrl':row['video_url'],
            'images':[r['url'] for r in imgs],'date':row['created_at'][:10]}

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
    cover_url = save_dataurl(d['coverImage'], ALLOWED_IMG) if d.get('coverImage') else None
    # embedUrl takes priority over file upload for video
    embed_url = d.get('embedUrl')
    if embed_url:
        video_url = embed_url
    else:
        video_url = save_dataurl(d['videoData'], ALLOWED_VID) if d.get('videoData') else None
    db = get_db()
    cur = db.execute('INSERT INTO projects(title,category,description,media_type,cover_url,video_url) VALUES(?,?,?,?,?,?)',
        (title,d.get('category','Social Media'),d.get('description',''),d.get('mediaType','image'),cover_url,video_url))
    pid = cur.lastrowid
    for i,img in enumerate(d.get('images',[])):
        url = save_dataurl(img, ALLOWED_IMG)
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
            if img.startswith('data:'):
                url = save_dataurl(img, ALLOWED_IMG)
                if url: db.execute('INSERT INTO project_images(project_id,url,sort_order) VALUES(?,?,?)',(pid,url,len(keep)+i))
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
        if img and img.startswith('data:'):
            old = db.execute(f"SELECT value FROM settings WHERE key='{store_key}'").fetchone()
            if old and old['value']: delete_file(old['value'])
            url = save_dataurl(img, ALLOWED_IMG)
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(store_key, url or ''))
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

# ─────────────────────────── VIMEO PROXY ─────────────────────────────────────
import urllib.request, urllib.error

@app.route('/api/vimeo/videos')
@login_required
def vimeo_videos():
    db   = get_db()
    row  = db.execute("SELECT value FROM settings WHERE key='vimeo_token'").fetchone()
    token = (row['value'] if row else '').strip()
    if not token:
        return jsonify({'error': 'Vimeo token not set'}), 400
    try:
        req = urllib.request.Request(
            'https://api.vimeo.com/me/videos?per_page=100&fields=uri,name,description,duration,pictures',
            headers={'Authorization': f'bearer {token}', 'Accept': 'application/vnd.vimeo.*+json;version=3.4'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        videos = []
        for v in data.get('data', []):
            vid_id = v['uri'].split('/')[-1]
            thumb  = ''
            pics   = v.get('pictures', {}).get('sizes', [])
            if pics:
                # pick medium thumbnail
                thumb = sorted(pics, key=lambda x: x.get('width',0))[min(2, len(pics)-1)].get('link','')
            videos.append({
                'id':          vid_id,
                'name':        v.get('name', ''),
                'description': v.get('description', '') or '',
                'duration':    v.get('duration', 0),
                'thumbnail':   thumb,
                'embed_url':   f'https://player.vimeo.com/video/{vid_id}?portrait=0&byline=0&title=0'
            })
        return jsonify({'videos': videos})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return jsonify({'error': f'Vimeo API error {e.code}', 'detail': body}), 502
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500

@app.route('/api/proxy-image', methods=['POST'])
@login_required
def proxy_image():
    """Fetch an external image and return as base64 data URL (for thumbnails)."""
    url = (request.get_json() or {}).get('url','').strip()
    if not url or not url.startswith('http'):
        return jsonify({'error': 'invalid url'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get_content_type() or 'image/jpeg'
            data = base64.b64encode(resp.read()).decode()
        return jsonify({'dataUrl': f'data:{content_type};base64,{data}'})
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500

# ─────────────────────────── STATIC ──────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

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
