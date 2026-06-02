#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""瑜伽馆运营管理系统 - Flask 后端（多账户版）"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
import os
import sys
import webbrowser
import threading
from datetime import datetime, timedelta
import random
import hashlib
import string
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'yoga_studio_secret_key_2026')

# 处理 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Render.com 云部署：使用持久化磁盘存储数据库
if os.path.isdir('/data'):
    DB_PATH = '/data/yoga.db'
else:
    DB_PATH = os.path.join(BASE_DIR, 'yoga.db')
# ======================== 自动备份功能 ========================
def _auto_backup():
    """启动时自动备份数据库"""
    backup_dir = os.path.join(BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    if os.path.exists(DB_PATH):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f'yoga_{timestamp}.db')
        
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        print(f'[自动备份] 已保存到: {backup_path}')

_auto_backup()

# ======================== 每日定时自动备份 ========================
def _scheduled_backup():
    """每日凌晨3点自动备份数据库（后台守护线程）"""
    backup_dir = os.path.join(BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    while True:
        now = datetime.now()
        next_backup = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_backup <= now:
            next_backup = next_backup + timedelta(days=1)
        wait_seconds = (next_backup - now).total_seconds()

        import time as _time
        _time.sleep(wait_seconds)

        if os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            import shutil
            backup_path = os.path.join(backup_dir, f'yoga_{timestamp}.db')
            shutil.copy2(DB_PATH, backup_path)
            print(f'[定时备份] 已保存到: {backup_path}')

_backup_thread = threading.Thread(target=_scheduled_backup, daemon=True)
_backup_thread.start()




# ======================== 认证装饰器 ========================

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function




# ======================== 密码哈希 ========================
def _hash_password(password):
    """简单的密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def _check_password(password, password_hash):
    """验证密码"""
    return _hash_password(password) == password_hash

def _generate_token(length=32):
    """生成随机令牌"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ======================== 辅助函数 ========================

def _month_range(today, offset=0):
    """计算月份范围，返回 (month_start, month_end, month_label)"""
    total_m = today.year * 12 + today.month - 1 - offset
    y = total_m // 12
    m_val = total_m % 12 + 1
    ms = f"{y}-{m_val:02d}-01"
    me = f"{y+1}-01-01" if m_val == 12 else f"{y}-{m_val+1:02d}-01"
    return ms, me, f"{y}-{m_val:02d}"


def _calc_cost_detail(db, month_start, month_end, user_id):
    """计算指定月份的成本明细（含所有支出，按大类展示）"""
    category_map = {
        '房租': '房租',
        '工资（全职）': '工资',
        '工资（兼职）': '工资',
        '水电费': '水电煤',
        '燃气费': '水电煤',
        '水电煤': '水电煤',
        '器材采购': '其他',
        '耗材用品': '其他',
        '营销推广': '其他',
        '培训学习': '其他',
        '其他支出': '其他',
        '其他': '其他',
    }
    display_categories = ['房租', '工资', '水电煤', '其他']
    
    # 初始化展示大类为0
    cost_detail = {cat: 0 for cat in display_categories}
    
    # 按原始分类统计所有支出
    all_rows = db.execute("""
        SELECT COALESCE(category, '其他'), COALESCE(SUM(amount), 0) FROM transactions
        WHERE type='expense' AND date >= ? AND date < ? AND user_id=?
        GROUP BY category
    """, (month_start, month_end, user_id)).fetchall()
    
    # 归到大类
    for raw_cat, total in all_rows:
        mapped = category_map.get(raw_cat, '其他')
        cost_detail[mapped] = cost_detail.get(mapped, 0) + total
    
    return cost_detail


def _calc_card_consume(db, month_start, month_end, user_id):
    """计算指定月份的消卡金额"""
    return db.execute("""
        SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
        JOIN class_records cr ON a.class_record_id = cr.id
        JOIN members m ON a.member_id = m.id
        WHERE cr.date >= ? AND cr.date < ? AND cr.user_id=?
    """, (month_start, month_end, user_id)).fetchone()[0]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        # 创建用户表
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                studio_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                reset_token TEXT DEFAULT '',
                reset_token_expiry TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 迁移：为旧表添加新字段（如果不存在）
        try:
            db.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
        except:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        except:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN reset_token TEXT DEFAULT ''")
        except:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN reset_token_expiry TEXT DEFAULT ''")
        except:
            pass
        
        # 创建配置表（用于存储初始现金流等）
        db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # 会员表（添加 user_id）
        db.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                card_type TEXT DEFAULT '',
                card_amount REAL DEFAULT 0,
                total_classes INTEGER DEFAULT 0,
                price_per_class REAL DEFAULT 0,
                classes_attended INTEGER DEFAULT 0,
                remaining_classes INTEGER DEFAULT 0,
                signup_date TEXT DEFAULT (date('now')),
                expiry_date TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                notes TEXT DEFAULT '',
                renewal_count INTEGER DEFAULT 0,
                renewal_amount REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 续卡记录表
        db.execute("""
            CREATE TABLE IF NOT EXISTS renewals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL DEFAULT 0,
                classes INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # 上课记录表（添加 user_id）
        db.execute("""
            CREATE TABLE IF NOT EXISTS class_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                time TEXT DEFAULT '',
                coach TEXT DEFAULT '',
                class_type TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 出勤表
        db.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_record_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                FOREIGN KEY (class_record_id) REFERENCES class_records(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # 交易表（添加 user_id）
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT DEFAULT '',
                amount REAL NOT NULL,
                member_id INTEGER,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """)

        # 预约表（添加 user_id）
        db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                class_date TEXT NOT NULL,
                class_time TEXT NOT NULL DEFAULT '',
                class_type TEXT DEFAULT '',
                coach TEXT DEFAULT '',
                status TEXT DEFAULT 'booked',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)
        
        # 迁移：为现有表添加 user_id 字段（如果不存在）
        for table in ['members', 'class_records', 'transactions', 'bookings', 'config']:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
            except:
                pass
        
        # 创建索引加速查询
        db.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_classes_user ON class_records(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_trans_user ON transactions(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)")


# ======================== 认证路由 ========================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面（支持用户名或手机号登录）"""
    if request.method == 'POST':
        login_id = request.form.get('username', '').strip()  # 可以是用户名或手机号
        password = request.form.get('password', '')

        if not login_id or not password:
            flash('请输入用户名/手机号和密码', 'error')
            return render_template('login.html')

        with get_db() as db:
            # 先按用户名查找，再按手机号查找
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (login_id,)
            ).fetchone()

            if not user:
                user = db.execute(
                    "SELECT * FROM users WHERE phone = ? AND phone != ''", (login_id,)
                ).fetchone()

        if user and _check_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['studio_name'] = user['studio_name']
            flash('登录成功', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('用户名/手机号或密码错误', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        studio_name = request.form.get('studio_name', '').strip()
        phone = request.form.get('phone', '').strip()

        # 验证
        if not username or not password:
            flash('请填写用户名和密码', 'error')
            return render_template('login.html', show_register=True)

        if len(password) < 6:
            flash('密码至少6位', 'error')
            return render_template('login.html', show_register=True)

        if password != password2:
            flash('两次密码不一致', 'error')
            return render_template('login.html', show_register=True)

        if not studio_name:
            flash('请输入瑜伽馆名称', 'error')
            return render_template('login.html', show_register=True)

        # 检查用户名是否已存在
        with get_db() as db:
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()

            if existing:
                flash('用户名已存在', 'error')
                return render_template('login.html', show_register=True)

            # 检查手机号是否已被使用
            if phone:
                phone_exists = db.execute(
                    "SELECT id FROM users WHERE phone = ? AND phone != ''", (phone,)
                ).fetchone()
                if phone_exists:
                    flash('该手机号已被其他账号使用', 'error')
                    return render_template('login.html', show_register=True)

            # 创建用户
            password_hash = _hash_password(password)
            db.execute(
                "INSERT INTO users (username, password_hash, studio_name, phone) VALUES (?, ?, ?, ?)",
                (username, password_hash, studio_name, phone)
            )
            user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # 设置默认初始现金流为0
            db.execute(
                "INSERT INTO config (key, value, user_id) VALUES ('initial_cash_flow', '0', ?)",
                (user_id,)
            )

        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template('login.html', show_register=True)


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('login'))


# ======================== 找回密码 ========================

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """找回密码 - 第一步：验证身份"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()

        if not username or not phone:
            flash('请填写用户名和手机号', 'error')
            return render_template('forgot_password.html')

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ? AND phone = ? AND phone != ''",
                (username, phone)
            ).fetchone()

            if not user:
                flash('用户名与手机号不匹配，请确认信息正确', 'error')
                return render_template('forgot_password.html')

            # 生成重置令牌（有效期30分钟）
            token = _generate_token(48)
            expiry = (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')

            db.execute(
                "UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?",
                (token, expiry, user['id'])
            )

            # 生成重置链接
            reset_url = url_for('reset_password', token=token, _external=True)
            flash(f'密码重置链接已生成（有效期30分钟）', 'success')
            return render_template('forgot_password.html', reset_url=reset_url, show_link=True)

    return render_template('forgot_password.html', show_link=False)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """找回密码 - 第二步：重置密码"""
    if not token:
        flash('无效的令牌', 'error')
        return redirect(url_for('login'))

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE reset_token = ? AND reset_token_expiry >= ?",
            (token, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        ).fetchone()

        if not user:
            # 检查是否是过期令牌
            expired_user = db.execute(
                "SELECT * FROM users WHERE reset_token = ?",
                (token,)
            ).fetchone()
            if expired_user:
                flash('重置链接已过期，请重新申请', 'error')
            else:
                flash('无效的重置链接', 'error')
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            password = request.form.get('password', '')
            password2 = request.form.get('password2', '')

            if not password or len(password) < 6:
                flash('密码至少6位', 'error')
                return render_template('reset_password.html', token=token)

            if password != password2:
                flash('两次密码不一致', 'error')
                return render_template('reset_password.html', token=token)

            # 更新密码并清除令牌
            password_hash = _hash_password(password)
            db.execute(
                "UPDATE users SET password_hash = ?, reset_token = '', reset_token_expiry = '' WHERE id = ?",
                (password_hash, user['id'])
            )

            flash('密码重置成功，请使用新密码登录', 'success')
            return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


@app.route('/api/user/update-phone', methods=['POST'])
@login_required
def api_update_phone():
    """更新当前用户的手机号"""
    user_id = session['user_id']
    data = request.get_json()
    phone = data.get('phone', '').strip()

    if not phone:
        return jsonify({'error': '请输入手机号'}), 400

    with get_db() as db:
        # 检查手机号是否已被其他用户使用
        existing = db.execute(
            "SELECT id FROM users WHERE phone = ? AND phone != '' AND id != ?",
            (phone, user_id)
        ).fetchone()
        if existing:
            return jsonify({'error': '该手机号已被其他账号使用'}), 400

        db.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
        return jsonify({'success': True, 'message': '手机号已更新'})


@app.route('/api/user/profile')
@login_required
def api_user_profile():
    """获取当前用户的详细信息"""
    user_id = session['user_id']
    with get_db() as db:
        user = db.execute(
            "SELECT id, username, studio_name, phone, email, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if user:
            return jsonify(dict(user))
        return jsonify({'error': '用户不存在'}), 404


@app.route('/sw.js')
def service_worker():
    """Service Worker (PWA 支持)"""
    from flask import send_from_directory
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


# ======================== 页面路由 ========================

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', studio_name=session.get('studio_name', ''))


@app.route('/members')
@login_required
def members():
    return render_template('members.html')


@app.route('/classes')
@login_required
def class_records():
    return render_template('class_records.html')


@app.route('/finance')
@login_required
def finance():
    return render_template('finance.html')


@app.route('/booking')
@login_required
def booking():
    return render_template('booking.html')


# ======================== API: 仪表盘数据 ========================

@app.route('/api/dashboard')
@login_required
def api_dashboard():
    user_id = session['user_id']
    with get_db() as db:
        today = datetime.now()
        ms, me, _ = _month_range(today, 0)

        # 本月收入（业绩）
        income = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ? AND user_id=?",
            (ms, me, user_id)).fetchone()[0]

        # 本月成本
        cost_detail = _calc_cost_detail(db, ms, me, user_id)
        total_cost = sum(cost_detail.values())

        # 本月消卡
        card_consume = _calc_card_consume(db, ms, me, user_id)

        # 负债 = 未消耗课时总值
        liability = db.execute(
            "SELECT COALESCE(SUM(remaining_classes * price_per_class), 0) FROM members WHERE status='active' AND user_id=?",
            (user_id,)
        ).fetchone()[0]

        # 活跃会员数
        active_members = db.execute(
            "SELECT COUNT(*) FROM members WHERE status='active' AND user_id=?", (user_id,)
        ).fetchone()[0]

        # 本月上课人次
        attend_count = db.execute("""
            SELECT COUNT(*) FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            WHERE cr.date >= ? AND cr.date < ? AND cr.user_id=?
        """, (ms, me, user_id)).fetchone()[0]

        # 累计现金流
        total_income = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND user_id=?", (user_id,)
        ).fetchone()[0]
        total_expense = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense' AND user_id=?", (user_id,)
        ).fetchone()[0]
        
        # 初始现金流
        initial_cf = float(db.execute(
            "SELECT COALESCE(CAST(value AS REAL), 0) FROM config WHERE key='initial_cash_flow' AND user_id=?",
            (user_id,)
        ).fetchone()[0] or 0)
        
        cash_balance = total_income - total_expense + initial_cf

        # 瑜伽馆评级
        studio_class = 'A' if cash_balance >= liability else 'B'

        # 近12个月趋势
        trend = []
        for i in range(11, -1, -1):
            tms, tme, label = _month_range(today, i)
            inc = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ? AND user_id=?",
                (tms, tme, user_id)).fetchone()[0]
            cost = sum(_calc_cost_detail(db, tms, tme, user_id).values())
            card = _calc_card_consume(db, tms, tme, user_id)
            trend.append({
                'month': label,
                'income': inc,
                'cost': cost,
                'card': card,
                'profit': card - cost,
                'cash_flow': inc - cost
            })

        # ==================== 三维度评估 ====================
        
        # 第一维度：现金流 vs 负债
        dimension1_class = 'A' if cash_balance >= liability else 'B'

        # 第二维度：现金流 vs 月平均成本
        # 计算过去6个月的月平均成本
        recent_costs = [t['cost'] for t in trend[-6:]]  # 最近6个月
        avg_monthly_cost = sum(recent_costs) / len(recent_costs) if recent_costs and sum(recent_costs) > 0 else 0
        
        if avg_monthly_cost > 0:
            if cash_balance >= 6 * avg_monthly_cost:
                dimension2_class = 'A'
            elif cash_balance >= 3 * avg_monthly_cost:
                dimension2_class = 'B'
            else:
                dimension2_class = 'C'
        else:
            # 如果没有成本数据，现金流为正就是A类
            dimension2_class = 'A' if cash_balance > 0 else 'C'

        # 第三维度：业绩 vs 消卡 vs 成本
        if income >= card_consume and card_consume >= total_cost:
            dimension3_class = 'A'
        elif card_consume >= income and income >= total_cost:
            dimension3_class = 'B'
        elif income >= total_cost and total_cost >= card_consume:
            dimension3_class = 'C'
        elif card_consume >= total_cost and total_cost >= income:
            dimension3_class = 'D'
        elif total_cost >= income and income >= card_consume:
            dimension3_class = 'E'
        elif total_cost >= card_consume and card_consume >= income:
            dimension3_class = 'F'
        else:
            dimension3_class = 'A'  # 默认
        # =====================================================

        # 会员卡类型分布
        card_dist = db.execute(
            "SELECT card_type, COUNT(*) as count FROM members WHERE status='active' AND user_id=? GROUP BY card_type",
            (user_id,)
        ).fetchall()
        card_dist = [{'label': r['card_type'], 'count': r['count']} for r in card_dist]

        return jsonify({
            'month_income': income,
            'month_cost': total_cost,
            'card_consumption': card_consume,
            'profit': card_consume - total_cost,
            'net_cash_flow': income - total_cost,
            'net_debt': income - card_consume,
            'cash_balance': cash_balance,
            'liability': liability,
            'studio_class': studio_class,
            'active_members': active_members,
            'attend_count': attend_count,
            'cost_detail': cost_detail,
            'trend': trend,
            'card_distribution': card_dist,
            'studio_name': session.get('studio_name', ''),
            'dimension1_class': dimension1_class,
            'dimension2_class': dimension2_class,
            'dimension3_class': dimension3_class,
            'avg_monthly_cost': round(avg_monthly_cost, 2),
        })


# ======================== API: 会员管理 ========================

@app.route('/api/members', methods=['GET'])
@login_required
def api_members_list():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')

    with get_db() as db:
        conditions = ['user_id = ?']
        params = [user_id]
        if keyword:
            conditions.append("(name LIKE ? OR phone LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where = "WHERE " + " AND ".join(conditions)
        
        total = db.execute(f"SELECT COUNT(*) FROM members {where}", params).fetchone()[0]
        rows = db.execute(f"SELECT * FROM members {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [per_page, offset]).fetchall()

        members_list = [dict(r) for r in rows]
        
        total_remaining = 0
        total_card_amount = 0
        for m in members_list:
            remaining = m.get('remaining_classes', 0) or 0
            price = m.get('price_per_class', 0) or 0
            if price > 0:
                total_remaining += remaining * price
            total_card_amount += m.get('card_amount', 0) or 0
        
        return jsonify({'members': members_list, 'total': total, 'page': page, 'per_page': per_page, 'total_remaining': total_remaining, 'total_card_amount': total_card_amount})


@app.route('/api/members', methods=['POST'])
@login_required
def api_members_create():
    user_id = session['user_id']
    data = request.get_json()
    total = data.get('total_classes', 0)
    amount = data.get('card_amount', 0)
    price = round(amount / total, 1) if total > 0 else 0

    with get_db() as db:
        db.execute("""INSERT INTO members
            (user_id, name, phone, card_type, card_amount, total_classes, price_per_class,
             classes_attended, remaining_classes, signup_date, expiry_date, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'active')""",
            (user_id, data['name'], data.get('phone', ''), data.get('card_type', ''),
             amount, total, price, total, data.get('signup_date', datetime.now().strftime('%Y-%m-%d')),
             data.get('expiry_date') or _auto_expiry(data.get('signup_date', datetime.now().strftime('%Y-%m-%d')), total), data.get('notes', '')))
        mid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 如果购卡金额 > 0，自动生成交易记录
        if amount > 0:
            db.execute("INSERT INTO transactions (user_id, date, type, category, amount, member_id, notes) VALUES (?, ?, 'income', '会费收入', ?, ?, ?)",
                       (user_id, data.get('signup_date', datetime.now().strftime('%Y-%m-%d')), amount, mid, f"{data['name']}办理{data.get('card_type','')}"))

        return jsonify({'success': True, 'id': mid})


def _auto_expiry(signup_str, total_classes):
    """每周2节课，自动计算到期日期"""
    try:
        signup = datetime.strptime(signup_str, '%Y-%m-%d')
    except:
        signup = datetime.now()
    if total_classes and total_classes > 0:
        weeks = total_classes / 2
        expiry = signup + timedelta(days=weeks * 7)
        return expiry.strftime('%Y-%m-%d')
    return ''


@app.route('/api/members/<int:mid>', methods=['GET'])
@login_required
def api_members_get(mid):
    user_id = session['user_id']
    with get_db() as db:
        member = db.execute("SELECT * FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not member:
            return jsonify({'error': '会员不存在'}), 404
        return jsonify(dict(member))


@app.route('/api/members/<int:mid>', methods=['PUT'])
@login_required
def api_members_update(mid):
    user_id = session['user_id']
    data = request.get_json()
    total = data.get('total_classes', 0)
    amount = data.get('card_amount', 0)
    price = round(amount / total, 1) if total > 0 else 0
    attended = data.get('classes_attended', 0)
    remaining = total - attended

    with get_db() as db:
        # 验证所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not m:
            return jsonify({'error': '无权限'}), 403
            
        db.execute("""UPDATE members SET
            name=?, phone=?, card_type=?, card_amount=?, total_classes=?,
            price_per_class=?, classes_attended=?, remaining_classes=?,
            signup_date=?, expiry_date=?, notes=?, status=?
            WHERE id=?""",
            (data['name'], data.get('phone', ''), data.get('card_type', ''),
             amount, total, price, attended,
             remaining, data.get('signup_date', ''), data.get('expiry_date', ''),
             data.get('notes', ''), data.get('status', 'active'), mid))
        return jsonify({'success': True})


@app.route('/api/members/<int:mid>', methods=['DELETE'])
@login_required
def api_members_delete(mid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not m:
            return jsonify({'error': '无权限'}), 403
            
        count = db.execute(
            "SELECT COUNT(*) FROM attendance WHERE member_id=?", (mid,)).fetchone()[0]
        if count > 0:
            return jsonify({'error': '该会员已有上课记录，无法删除。如需停用，请将会员状态改为"已过期"'}), 400
        db.execute("DELETE FROM members WHERE id=?", (mid,))
        return jsonify({'success': True})


@app.route('/api/members/<int:mid>/remaining', methods=['PATCH'])
@login_required
def api_members_update_remaining(mid):
    user_id = session['user_id']
    data = request.get_json()
    remaining = data.get('remaining_classes')
    if remaining is None:
        return jsonify({'error': '缺少剩余课时参数'}), 400
    
    with get_db() as db:
        # 验证所有权
        member = db.execute("SELECT total_classes FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not member:
            return jsonify({'error': '会员不存在或无权限'}), 404
        total = member['total_classes'] or 0
        attended = max(0, total - int(remaining))
        db.execute("UPDATE members SET remaining_classes = ?, classes_attended = ? WHERE id=?",
                   (int(remaining), attended, mid))
        return jsonify({'success': True})


@app.route('/api/members/<int:mid>/history')
@login_required
def api_members_history(mid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not m:
            return jsonify([]), 403
            
        rows = db.execute("""
            SELECT cr.date, cr.time, cr.coach, cr.class_type, cr.id as class_id
            FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            WHERE a.member_id = ? AND cr.user_id=?
            ORDER BY cr.date DESC, cr.time DESC
            LIMIT 100
        """, (mid, user_id)).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 续卡记录 ========================

@app.route('/api/renewals', methods=['GET'])
@login_required
def api_renewals_list():
    user_id = session['user_id']
    member_id = request.args.get('member_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with get_db() as db:
        conditions = ['m.user_id = ?']
        params = [user_id]
        if member_id:
            conditions.append("r.member_id = ?")
            params.append(member_id)

        where = "WHERE " + " AND ".join(conditions)

        total = db.execute(f"SELECT COUNT(*) FROM renewals r JOIN members m ON r.member_id = m.id {where}", params).fetchone()[0]
        rows = db.execute(f"""
            SELECT r.*, m.name as member_name
            FROM renewals r
            JOIN members m ON r.member_id = m.id
            {where}
            ORDER BY r.date DESC, r.id DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        return jsonify({'renewals': [dict(r) for r in rows], 'total': total, 'page': page, 'per_page': per_page})


@app.route('/api/renewals', methods=['POST'])
@login_required
def api_renewals_create():
    user_id = session['user_id']
    data = request.get_json()
    member_id = data.get('member_id')
    amount = data.get('amount', 0)
    classes = data.get('classes', 0)
    notes = data.get('notes', '')

    with get_db() as db:
        # 验证会员所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (member_id, user_id)).fetchone()
        if not m:
            return jsonify({'error': '会员不存在或无权限'}), 403
            
        db.execute("""
            INSERT INTO renewals (member_id, date, amount, classes, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (member_id, data.get('date', datetime.now().strftime('%Y-%m-%d')), amount, classes, notes))
        rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute("""
            UPDATE members SET
                total_classes = total_classes + ?,
                remaining_classes = remaining_classes + ?,
                renewal_count = renewal_count + 1,
                renewal_amount = renewal_amount + ?
            WHERE id = ?
        """, (classes, classes, amount, member_id))

        return jsonify({'success': True, 'id': rid})


@app.route('/api/renewals/<int:rid>', methods=['DELETE'])
@login_required
def api_renewals_delete(rid):
    user_id = session['user_id']
    with get_db() as db:
        row = db.execute("""
            SELECT r.* FROM renewals r
            JOIN members m ON r.member_id = m.id
            WHERE r.id = ? AND m.user_id = ?
        """, (rid, user_id)).fetchone()
        
        if not row:
            return jsonify({'success': False, 'error': '记录不存在或无权限'})
        rec = dict(row)

        db.execute("""
            UPDATE members SET
                total_classes = total_classes - ?,
                remaining_classes = remaining_classes - ?,
                renewal_count = MAX(0, renewal_count - 1),
                renewal_amount = MAX(0, renewal_amount - ?)
            WHERE id = ?
        """, (rec['classes'], rec['classes'], rec['amount'], rec['member_id']))

        db.execute("DELETE FROM renewals WHERE id = ?", (rid,))
        return jsonify({'success': True})


@app.route('/api/renewals/member/<int:mid>')
@login_required
def api_renewals_by_member(mid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
        if not m:
            return jsonify([]), 403
            
        rows = db.execute("""
            SELECT r.*, m.name as member_name
            FROM renewals r
            JOIN members m ON r.member_id = m.id
            WHERE r.member_id = ?
            ORDER BY r.date DESC
        """, (mid,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 上课记录 ========================

@app.route('/api/classes', methods=['GET'])
@login_required
def api_classes_list():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM class_records WHERE user_id=?", (user_id,)).fetchone()[0]
        rows = db.execute("""
            SELECT cr.*, GROUP_CONCAT(m.name, '、') as member_names,
                   COUNT(a.id) as attend_count
            FROM class_records cr
            LEFT JOIN attendance a ON cr.id = a.class_record_id
            LEFT JOIN members m ON a.member_id = m.id
            WHERE cr.user_id = ?
            GROUP BY cr.id
            ORDER BY cr.date DESC, cr.id DESC
            LIMIT ? OFFSET ?
        """, (user_id, per_page, offset)).fetchall()

        class_list = []
        for r in rows:
            item = dict(r)
            item['member_names'] = item['member_names'] or ''
            class_list.append(item)

        return jsonify({'classes': class_list, 'total': total, 'page': page, 'per_page': per_page})


@app.route('/api/classes', methods=['POST'])
@login_required
def api_classes_create():
    user_id = session['user_id']
    data = request.get_json()
    member_ids = data.get('member_ids', [])

    with get_db() as db:
        db.execute("INSERT INTO class_records (user_id, date, time, coach, class_type, notes) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, data['date'], data.get('time', ''), data.get('coach', ''), 
                    data.get('class_type', ''), data.get('notes', '')))
        cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for mid in member_ids:
            # 验证会员所有权
            m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (mid, user_id)).fetchone()
            if m:
                db.execute("INSERT INTO attendance (class_record_id, member_id) VALUES (?, ?)", (cid, mid))
                db.execute("UPDATE members SET classes_attended = classes_attended + 1, remaining_classes = remaining_classes - 1 WHERE id = ? AND remaining_classes > 0",
                           (mid,))

        return jsonify({'success': True, 'id': cid})


@app.route('/api/classes/<int:cid>', methods=['DELETE'])
@login_required
def api_classes_delete(cid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        cr = db.execute("SELECT id FROM class_records WHERE id=? AND user_id=?", (cid, user_id)).fetchone()
        if not cr:
            return jsonify({'error': '无权限'}), 403
            
        attendees = db.execute("SELECT member_id FROM attendance WHERE class_record_id=?", (cid,)).fetchall()
        for a in attendees:
            db.execute("UPDATE members SET classes_attended = MAX(0, classes_attended - 1), remaining_classes = remaining_classes + 1 WHERE id=?",
                       (a['member_id'],))
        db.execute("DELETE FROM class_records WHERE id=?", (cid,))
        return jsonify({'success': True})


@app.route('/api/classes/today')
@login_required
def api_classes_today():
    user_id = session['user_id']
    # 支持传入日期参数，默认今天
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    with get_db() as db:
        rows = db.execute("""
            SELECT cr.id as class_id, cr.date, cr.time, cr.coach, cr.class_type, cr.notes,
                   m.id as member_id, m.name as member_name, m.card_type, m.price_per_class
            FROM class_records cr
            LEFT JOIN attendance a ON cr.id = a.class_record_id
            LEFT JOIN members m ON a.member_id = m.id
            WHERE cr.date = ? AND cr.user_id = ?
            ORDER BY cr.time DESC, cr.id DESC
        """, (date_str, user_id)).fetchall()

        classes = {}
        for r in rows:
            cid = r['class_id']
            if cid not in classes:
                classes[cid] = {
                    'class_id': cid,
                    'date': r['date'],
                    'time': r['time'],
                    'coach': r['coach'],
                    'class_type': r['class_type'],
                    'notes': r['notes'],
                    'members': []
                }
            if r['member_id']:
                classes[cid]['members'].append({
                    'id': r['member_id'],
                    'name': r['member_name'],
                    'card_type': r['card_type'],
                    'price_per_class': r['price_per_class']
                })

        return jsonify({
            'date': date_str,
            'records': list(classes.values()),
            'total': len(classes)
        })


@app.route('/api/classes/<int:cid>', methods=['PUT'])
@login_required
def api_classes_update(cid):
    user_id = session['user_id']
    data = request.get_json()
    with get_db() as db:
        # 验证所有权
        cr = db.execute("SELECT id FROM class_records WHERE id=? AND user_id=?", (cid, user_id)).fetchone()
        if not cr:
            return jsonify({'error': '无权限'}), 403
            
        db.execute("UPDATE class_records SET date=?, time=?, class_type=?, coach=?, notes=? WHERE id=?",
                   (data.get('date', ''), data.get('time', ''),
                    data.get('class_type', ''), data.get('coach', ''), 
                    data.get('notes', ''), cid))
        return jsonify({'success': True})


# ======================== API: 财务管理 ========================

@app.route('/api/transactions', methods=['GET'])
@login_required
def api_transactions_list():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    ttype = request.args.get('type', '')
    month = request.args.get('month', '')

    with get_db() as db:
        conditions = ['t.user_id = ?']
        params = [user_id]
        if ttype:
            conditions.append("t.type=?")
            params.append(ttype)
        if month:
            conditions.append("t.date LIKE ?")
            params.append(f"{month}%")

        where = "WHERE " + " AND ".join(conditions)

        total = db.execute(
            f"SELECT COUNT(*) FROM transactions t {where}", params).fetchone()[0]

        rows = db.execute(f"""
            SELECT t.*, m.name as member_name
            FROM transactions t
            LEFT JOIN members m ON t.member_id = m.id
            {where}
            ORDER BY t.date DESC, t.id DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        return jsonify({
            'transactions': [dict(r) for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page
        })


@app.route('/api/transactions', methods=['POST'])
@login_required
def api_transactions_create():
    user_id = session['user_id']
    data = request.get_json()
    with get_db() as db:
        db.execute("INSERT INTO transactions (user_id, date, type, category, amount, notes, member_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, data['date'], data['type'], data.get('category', ''),
                    data['amount'], data.get('notes', ''), data.get('member_id') or None))
        tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({'success': True, 'id': tid})


@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
@login_required
def api_transactions_delete(tid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        t = db.execute("SELECT id FROM transactions WHERE id=? AND user_id=?", (tid, user_id)).fetchone()
        if not t:
            return jsonify({'error': '无权限'}), 403
        db.execute("DELETE FROM transactions WHERE id=?", (tid,))
        return jsonify({'success': True})


@app.route('/api/finance/summary')
@login_required
def api_finance_summary():
    user_id = session['user_id']
    with get_db() as db:
        today = datetime.now()

        monthly = []
        for i in range(5, -1, -1):
            total_m = today.year * 12 + today.month - 1 - i
            y = total_m // 12
            m_val = total_m % 12 + 1
            ms = f"{y}-{m_val:02d}-01"
            if m_val == 12:
                me = f"{y+1}-01-01"
            else:
                me = f"{y}-{m_val+1:02d}-01"
            inc = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ? AND user_id=?",
                (ms, me, user_id)).fetchone()[0]
            exp = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense' AND date >= ? AND date < ? AND user_id=?",
                (ms, me, user_id)).fetchone()[0]
            
            cost_rows = db.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM transactions 
                WHERE type='expense' AND date >= ? AND date < ? AND user_id=?
            """, (ms, me, user_id)).fetchone()[0]
            
            card_rows = db.execute("""
                SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
                JOIN class_records cr ON a.class_record_id = cr.id
                JOIN members m ON a.member_id = m.id
                WHERE cr.date >= ? AND cr.date < ? AND cr.user_id=?
            """, (ms, me, user_id)).fetchone()[0]
            
            monthly.append({
                'month': f"{y}-{m_val:02d}",
                'income': inc,
                'expense': exp,
                'profit': inc - exp,
                'cost': cost_rows,
                'card_consumed': card_rows,
                'net_cash_flow': inc - cost_rows,
                'net_debt': inc - card_rows
            })

        month_start = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month.strftime('%Y-%m-%d')
        
        cost_detail = _calc_cost_detail(db, month_start, month_end, user_id)
        total_cost = sum(cost_detail.values())
        
        card_consume = db.execute("""
            SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            JOIN members m ON a.member_id = m.id
            WHERE cr.date >= ? AND cr.date < ? AND cr.user_id=?
        """, (month_start, month_end, user_id)).fetchone()[0]

        month_income = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type='income' AND date >= ? AND date < ? AND user_id=?
        """, (month_start, month_end, user_id)).fetchone()[0]
        
        liability = db.execute(
            "SELECT COALESCE(SUM(remaining_classes * price_per_class), 0) FROM members WHERE status='active' AND user_id=?",
            (user_id,)
        ).fetchone()[0]

        initial_cf = float(db.execute(
            "SELECT COALESCE(CAST(value AS REAL), 0) FROM config WHERE key='initial_cash_flow' AND user_id=?",
            (user_id,)
        ).fetchone()[0] or 0)
        
        total_income = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND user_id=?", (user_id,)
        ).fetchone()[0]
        total_expense = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense' AND user_id=?", (user_id,)
        ).fetchone()[0]

        return jsonify({
            'monthly': monthly,
            'card_consumption': card_consume,
            'cost_detail': cost_detail,
            'total_cost': total_cost,
            'month_income': month_income,
            'profit': card_consume - total_cost,
            'net_cash_flow': month_income - total_cost,
            'net_debt': month_income - card_consume,
            'cash_balance': total_income - total_expense + initial_cf,
            'initial_cash_flow': initial_cf,
            'liability': liability,
            'total_income': total_income,
            'total_expense': total_expense,
            'total_profit': total_income - total_expense,
            'studio_class': 'A' if (total_income - total_expense + initial_cf) >= liability else 'B',
            'studio_name': session.get('studio_name', ''),
        })

@app.route('/api/finance/config', methods=['POST'])
@login_required
def api_finance_config():
    user_id = session['user_id']
    data = request.get_json()
    key = data.get('key', '')
    value = str(data.get('value', '0'))
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO config (key, value, user_id) VALUES (?, ?, ?)", (key, value, user_id))
    return jsonify({'success': True, 'key': key, 'value': value})

@app.route('/api/members/all')
@login_required
def api_members_all():
    user_id = session['user_id']
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, phone, card_type, remaining_classes, status FROM members WHERE status='active' AND user_id=? ORDER BY name",
            (user_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 预约管理 ========================

@app.route('/api/bookings', methods=['GET'])
@login_required
def api_bookings_list():
    user_id = session['user_id']
    date_filter = request.args.get('date', '')
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = 20

    conditions = ['b.user_id = ?']
    params = [user_id]
    if date_filter:
        conditions.append('b.class_date = ?')
        params.append(date_filter)
    if status:
        conditions.append('b.status = ?')
        params.append(status)

    where = ' WHERE ' + ' AND '.join(conditions)

    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM bookings b{where}", params).fetchone()[0]
        rows = db.execute(f"""
            SELECT b.id, b.class_date, b.class_time, b.class_type, b.coach, b.status, b.notes,
                   m.id as member_id, m.name as member_name, m.phone as member_phone,
                   m.card_type, m.remaining_classes
            FROM bookings b
            LEFT JOIN members m ON b.member_id = m.id
            {where}
            ORDER BY b.class_date, b.class_time
            LIMIT ? OFFSET ?
        """, params + [per_page, (page - 1) * per_page]).fetchall()
        return jsonify({
            'bookings': [dict(r) for r in rows],
            'total': total, 'page': page, 'per_page': per_page
        })


@app.route('/api/bookings', methods=['POST'])
@login_required
def api_bookings_create():
    user_id = session['user_id']
    data = request.get_json()
    member_id = data.get('member_id')
    if not member_id:
        return jsonify({'error': '请选择会员'}), 400

    with get_db() as db:
        # 验证会员所有权
        m = db.execute("SELECT id FROM members WHERE id=? AND user_id=?", (member_id, user_id)).fetchone()
        if not m:
            return jsonify({'error': '会员不存在或无权限'}), 403
            
        existing = db.execute(
            "SELECT id FROM bookings WHERE member_id=? AND class_date=? AND class_time=? AND status='booked' AND user_id=?",
            (member_id, data['class_date'], data.get('class_time', ''), user_id)
        ).fetchone()
        if existing:
            return jsonify({'error': '该会员此时段已有预约'}), 400

        db.execute("""INSERT INTO bookings
            (user_id, member_id, class_date, class_time, class_type, coach, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'booked', ?)""",
            (user_id, member_id, data['class_date'], data.get('class_time', ''),
             data.get('class_type', ''), data.get('coach', ''), data.get('notes', '')))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['PUT'])
@login_required
def api_bookings_update(bid):
    user_id = session['user_id']
    data = request.get_json()
    with get_db() as db:
        # 验证所有权
        b = db.execute("SELECT id FROM bookings WHERE id=? AND user_id=?", (bid, user_id)).fetchone()
        if not b:
            return jsonify({'error': '无权限'}), 403
        db.execute("UPDATE bookings SET status=?, notes=? WHERE id=?",
                   (data.get('status', 'booked'), data.get('notes', ''), bid))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['DELETE'])
@login_required
def api_bookings_delete(bid):
    user_id = session['user_id']
    with get_db() as db:
        # 验证所有权
        b = db.execute("SELECT id FROM bookings WHERE id=? AND user_id=?", (bid, user_id)).fetchone()
        if not b:
            return jsonify({'error': '无权限'}), 403
        db.execute("DELETE FROM bookings WHERE id=?", (bid,))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['GET'])
@login_required
def api_bookings_get(bid):
    user_id = session['user_id']
    with get_db() as db:
        row = db.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (bid, user_id)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({'error': '预约不存在'}), 404


@app.route('/api/bookings/<int:bid>/attend', methods=['POST'])
@login_required
def api_bookings_attend(bid):
    user_id = session['user_id']
    with get_db() as db:
        booking = db.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (bid, user_id)).fetchone()
        if not booking:
            return jsonify({'error': '预约不存在或无权限'}), 404
        
        if booking['status'] != 'booked':
            return jsonify({'error': '该预约已处理'}), 400
        
        member_id = booking['member_id']
        
        member = db.execute("SELECT remaining_classes FROM members WHERE id=? AND user_id=?", (member_id, user_id)).fetchone()
        if not member or member['remaining_classes'] <= 0:
            return jsonify({'error': '会员课时不足'}), 400
        
        db.execute("""INSERT INTO class_records (user_id, date, time, coach, class_type, notes)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                   (user_id, booking['class_date'], booking['class_time'],
                    booking['coach'], booking['class_type'],
                    f"预约签到 - {booking['notes'] or ''}"))
        record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        db.execute("INSERT INTO attendance (class_record_id, member_id) VALUES (?, ?)",
                   (record_id, member_id))
        
        db.execute("""UPDATE members 
                     SET classes_attended = classes_attended + 1,
                         remaining_classes = remaining_classes - 1
                     WHERE id=?""", (member_id,))
        
        db.execute("UPDATE bookings SET status='attended' WHERE id=?", (bid,))
        
        return jsonify({'success': True, 'record_id': record_id})


@app.route('/api/bookings/date/<date_str>')
@login_required
def api_bookings_by_date(date_str):
    user_id = session['user_id']
    with get_db() as db:
        rows = db.execute("""
            SELECT b.id, b.class_date, b.class_time, b.class_type, b.coach, b.status,
                   m.id as member_id, m.name as member_name, m.card_type
            FROM bookings b
            LEFT JOIN members m ON b.member_id = m.id
            WHERE b.class_date = ? AND b.status = 'booked' AND b.user_id = ?
            ORDER BY b.class_time
        """, (date_str, user_id)).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 当前用户信息 ========================

@app.route('/api/user/info')
@login_required
def api_user_info():
    return jsonify({
        'user_id': session.get('user_id'),
        'username': session.get('username'),
        'studio_name': session.get('studio_name')
    })


# ======================== 数据库迁移（安全上传本地数据到 Render） ========================

@app.route('/migrate')
def migrate_page():
    """数据库迁移页面"""
    return render_template('migrate.html')


@app.route('/api/migrate-database', methods=['POST'])
def api_migrate_database():
    """上传本地数据库到服务器（需要管理员密码验证）"""
    # 验证管理员密码（默认 Migrate@2026，可在环境变量中修改）
    admin_pass = request.form.get('admin_pass', '')
    expected_pass = os.environ.get('MIGRATE_ADMIN_PASS', 'Migrate@2026')
    if admin_pass != expected_pass:
        return jsonify({'success': False, 'error': '管理员密码错误'}), 403

    if 'db_file' not in request.files:
        return jsonify({'success': False, 'error': '请选择数据库文件'}), 400

    file = request.files['db_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    if not file.filename.endswith('.db'):
        return jsonify({'success': False, 'error': '请选择 .db 数据库文件'}), 400

    try:
        # 1. 备份当前数据库（如果有）
        if os.path.exists(DB_PATH):
            backup_dir = os.path.dirname(DB_PATH)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            import shutil
            backup_path = os.path.join(backup_dir, f'pre_migration_backup_{timestamp}.db')
            shutil.copy2(DB_PATH, backup_path)

        # 2. 保存上传的数据库
        file.save(DB_PATH)

        # 3. 验证数据库完整性
        try:
            with get_db() as db:
                db.execute("SELECT COUNT(*) FROM users")
                user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                member_count = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
                class_count = db.execute("SELECT COUNT(*) FROM class_records").fetchone()[0]
                trans_count = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                attend_count = db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        except Exception as e:
            # 恢复备份
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, DB_PATH)
            return jsonify({
                'success': False,
                'error': f'数据库文件无效：{str(e)}'
            }), 400

        return jsonify({
            'success': True,
            'message': '数据库迁移成功！现有数据已备份。',
            'stats': {
                'users': user_count,
                'members': member_count,
                'classes': class_count,
                'transactions': trans_count,
                'attendance': attend_count
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'迁移失败：{str(e)}'}), 500


# ======================== 手机入口 ========================

@app.route('/mobile')
def mobile_entry():
    """手机入口页面"""
    return render_template('mobile.html')

@app.route('/api/tunnel-url')
def api_tunnel_url():
    """返回当前公网隧道地址"""
    import subprocess
    try:
        with open('/tmp/cloudflared.log', 'r') as f:
            content = f.read()
            import re
            match = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', content)
            if match:
                return jsonify({'url': match.group()})
    except:
        pass
    # 返回当前请求的 origin
    return jsonify({'url': request.host_url.rstrip('/')})


# ======================== 启动 ========================

def open_browser():
    """延迟打开浏览器"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')


# 初始化数据库（gunicorn 导入时也会执行，确保表结构存在）
init_db()

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("\n" + "=" * 40)
    print("  🧘 瑜伽馆运营管理系统（多账户版）")
    print("  📍 访问地址: http://127.0.0.1:5000")
    print("  👤 首次使用请注册账户")
    print("  ⌨️  按 Ctrl+C 停止服务器")
    print("=" * 40 + "\n")
    
    # 使用环境变量 PORT（Render.com 设置），默认 5000
    port = int(os.environ.get('PORT', 5000))
    # host='0.0.0.0' 允许局域网内其他设备（包括手机）访问
    app.run(host='0.0.0.0', port=port, debug=False)