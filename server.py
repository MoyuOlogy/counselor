#!/usr/bin/env python3
"""辅导员学生管理系统 - 后端服务 (零依赖) - Session 认证版"""

import json
import os
import re
import sys
import html
import uuid
import secrets
import subprocess
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HTPASSWD_PATH = os.environ.get('COUNSELOR_HTPASSWD', '/etc/nginx/.htpasswd')
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- Session 管理 ----------
# { token: { 'username': str, 'expires': float } }
sessions = {}

SESSION_TTL = 86400  # 24 小时


def create_session(username):
    """创建登录 session"""
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        'username': username,
        'expires': time.time() + SESSION_TTL,
    }
    return token


def validate_session(token):
    """验证 session 是否有效"""
    if not token or token not in sessions:
        return None
    sess = sessions[token]
    if time.time() > sess['expires']:
        del sessions[token]
        return None
    return sess


def cleanup_sessions():
    """清理过期 session"""
    now = time.time()
    expired = [t for t, s in sessions.items() if now > s['expires']]
    for t in expired:
        del sessions[t]


def verify_password(username, password):
    """通过 htpasswd 文件验证密码"""
    try:
        result = subprocess.run(
            ['htpasswd', '-v', HTPASSWD_PATH, username],
            input=(password + '\n').encode(),
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------- 输入校验规则 ----------
MAX_STRING_LEN = 200
MAX_NOTE_LEN = 1000
VALID_GENDERS = {'男', '女'}
VALID_CLASSES = {'2021级', '2022级', '2023级', '2024级', '2025级', '2026级'}
VALID_POLITICAL = {'群众', '共青团员', '中共预备党员', '中共党员'}
VALID_SCHEDULE_CATEGORIES = {'blue', 'green', 'yellow', 'red'}
VALID_REMIND = {'0', '15', '30', '60', '1440'}
CAT_NAMES = {'资助', '奖助', '学业', '党建', '心理'}
VALID_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
VALID_TIME_RE = re.compile(r'^\d{2}:\d{2}$')


def sanitize_str(val, max_len=MAX_STRING_LEN):
    """清理字符串：去除首尾空白、截断长度、HTML 转义"""
    if not isinstance(val, str):
        return ''
    val = val.strip()
    val = html.escape(val, quote=True)
    if len(val) > max_len:
        val = val[:max_len]
    return val


def validate_student(data):
    """校验学生数据，返回 (cleaned_data, error_msg)"""
    errors = []
    student_id = sanitize_str(data.get('studentId', ''), 50)
    name = sanitize_str(data.get('name', ''), 50)
    if not student_id:
        errors.append('学号不能为空')
    if not name:
        errors.append('姓名不能为空')
    if not student_id or not name:
        return None, '、'.join(errors)

    cleaned = {
        'studentId': student_id,
        'name': name,
        'gender': data.get('gender', '男') if data.get('gender') in VALID_GENDERS else '男',
        'className': data.get('className', '2024级') if data.get('className') in VALID_CLASSES else '2024级',
        'phone': sanitize_str(data.get('phone', ''), 20),
        'dorm': sanitize_str(data.get('dorm', ''), 30),
        'political': data.get('political', '群众') if data.get('political') in VALID_POLITICAL else '群众',
        'birthday': data.get('birthday', '') if (isinstance(data.get('birthday'), str) and VALID_DATE_RE.match(data.get('birthday', ''))) else '',
        'note': sanitize_str(data.get('note', ''), MAX_NOTE_LEN),
        'categories': {},
    }

    raw_cats = data.get('categories', {})
    if isinstance(raw_cats, dict):
        for cat in CAT_NAMES:
            cat_data = raw_cats.get(cat, {})
            if isinstance(cat_data, dict):
                cleaned['categories'][cat] = {
                    'enabled': bool(cat_data.get('enabled', False)),
                    'note': sanitize_str(cat_data.get('note', ''), 200),
                }
            else:
                cleaned['categories'][cat] = {'enabled': False, 'note': ''}
    return cleaned, None


def validate_work(data):
    """校验工作记录数据"""
    title = sanitize_str(data.get('title', ''), 100)
    if not title:
        return None, '工作标题不能为空'
    cleaned = {
        'title': title,
        'content': sanitize_str(data.get('content', ''), MAX_NOTE_LEN),
        'date': data.get('date', '') if (isinstance(data.get('date'), str) and VALID_DATE_RE.match(data.get('date', ''))) else '',
        'note': sanitize_str(data.get('note', ''), MAX_NOTE_LEN),
    }
    return cleaned, None


def validate_schedule(data):
    """校验日程数据"""
    title = sanitize_str(data.get('title', ''), 100)
    date = data.get('date', '')
    if not title:
        return None, '日程标题不能为空'
    if not date or not VALID_DATE_RE.match(date):
        return None, '日期格式无效'
    cleaned = {
        'title': title,
        'date': date,
        'time': data.get('time', '') if (isinstance(data.get('time'), str) and VALID_TIME_RE.match(data.get('time', ''))) else '',
        'category': data.get('category', 'blue') if data.get('category') in VALID_SCHEDULE_CATEGORIES else 'blue',
        'remind': data.get('remind', '0') if data.get('remind') in VALID_REMIND else '0',
        'note': sanitize_str(data.get('note', ''), MAX_NOTE_LEN),
    }
    return cleaned, None


# ---------- 数据读写 ----------
def load(name):
    path = os.path.join(DATA_DIR, f'{name}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save(name, data):
    path = os.path.join(DATA_DIR, f'{name}.json')
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def gen_id():
    return str(uuid.uuid4())


# ---------- 路由 ----------
ROUTES = {
    'students':  {'validator': validate_student, 'key': 'students'},
    'schedules': {'validator': validate_schedule, 'key': 'schedules'},
    'works':     {'validator': validate_work, 'key': 'works'},
}

FIXED_ORIGIN = os.environ.get('COUNSELOR_ORIGIN', 'http://localhost:8080')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    # ---------- 认证检查 ----------
    def _get_token(self):
        """从请求头提取 Bearer token"""
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            return auth[7:]
        return None

    def _check_auth(self):
        """检查 session token 是否有效"""
        token = self._get_token()
        return validate_session(token) is not None

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', FIXED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization,Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        if length > 5 * 1024 * 1024:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

    def _match(self, pattern):
        return re.match(pattern, self.path)

    def _check_auth_or_reject(self):
        if not self._check_auth():
            self._json(401, {'error': '未授权，请先登录'})
            return True
        return False

    def _get_client_ip(self):
        forwarded = self.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return self.client_address[0]

    # --- CORS preflight ---
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', FIXED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization,Content-Type')
        self.end_headers()

    def _handle_auto_login(self):
        """自动登录：从 Authorization 头读取 basic auth，验证后创建 session"""
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Basic '):
            try:
                import base64
                decoded = base64.b64decode(auth[6:]).decode('utf-8')
                username, password = decoded.split(':', 1)
                if verify_password(username, password):
                    token = create_session(username)
                    return self._json(200, {
                        'token': token,
                        'expiresIn': SESSION_TTL,
                        'username': username,
                    })
            except Exception:
                pass
        return self._json(401, {'error': '需要登录'})

    def do_GET(self):
        # /api/auto-login: 自动登录（读取 basic auth 头）
        if self.path == '/api/auto-login':
            return self._handle_auto_login()

        if self._check_auth_or_reject():
            return
        # 定期清理过期 session
        cleanup_sessions()

        for name, cfg in ROUTES.items():
            if self.path == f'/api/{name}':
                items = load(cfg['key'])
                return self._json(200, items)

        for name, cfg in ROUTES.items():
            m = self._match(f'/api/{name}/([^/]+)$')
            if m:
                items = load(cfg['key'])
                item = next((i for i in items if i['id'] == m.group(1)), None)
                if item:
                    return self._json(200, item)
                return self._json(404, {'error': 'not found'})

        if self.path == '/' or self.path == '':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        # ---------- 自动登录（basic auth） ----------
        if self.path == '/api/auto-login':
            return self._handle_auto_login()

        # ---------- 其他 API 需要认证 ----------
        if self._check_auth_or_reject():
            return

        for name, cfg in ROUTES.items():
            if self.path == f'/api/{name}':
                body = self._read_body()
                if body is None:
                    return self._json(413, {'error': '请求体过大'})
                if cfg['validator']:
                    cleaned, err = cfg['validator'](body)
                    if err:
                        return self._json(400, {'error': err})
                else:
                    cleaned = body
                items = load(cfg['key'])
                cleaned['id'] = gen_id()
                cleaned['createdAt'] = datetime.now().isoformat()
                cleaned['updatedAt'] = cleaned['createdAt']
                items.append(cleaned)
                save(cfg['key'], items)
                return self._json(201, cleaned)
        self._json(404, {'error': 'not found'})

    def do_PUT(self):
        if self._check_auth_or_reject():
            return
        for name, cfg in ROUTES.items():
            m = self._match(f'/api/{name}/([^/]+)$')
            if m:
                body = self._read_body()
                if body is None:
                    return self._json(413, {'error': '请求体过大'})
                items = load(cfg['key'])
                idx = next((i for i, x in enumerate(items) if x['id'] == m.group(1)), None)
                if idx is None:
                    return self._json(404, {'error': 'not found'})
                if cfg['validator']:
                    cleaned, err = cfg['validator'](body)
                    if err:
                        return self._json(400, {'error': err})
                else:
                    cleaned = body
                cleaned['id'] = items[idx]['id']
                cleaned['createdAt'] = items[idx].get('createdAt', '')
                cleaned['updatedAt'] = datetime.now().isoformat()
                items[idx] = cleaned
                save(cfg['key'], items)
                return self._json(200, cleaned)
        self._json(404, {'error': 'not found'})

    def do_DELETE(self):
        if self._check_auth_or_reject():
            return
        for name, cfg in ROUTES.items():
            m = self._match(f'/api/{name}/([^/]+)$')
            if m:
                items = load(cfg['key'])
                new_items = [i for i in items if i['id'] != m.group(1)]
                if len(new_items) == len(items):
                    return self._json(404, {'error': 'not found'})
                save(cfg['key'], new_items)
                return self._json(200, {'ok': True})
        self._json(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]}\n")


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(('127.0.0.1', port), Handler)
    print(f'🎓 辅导员系统启动 (Session 认证版): http://127.0.0.1:{port}')
    print(f'📂 数据目录: {DATA_DIR}')
    server.serve_forever()
