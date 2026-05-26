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
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'yoga_studio_secret_key_2026'  # 生产环境应使用环境变量

# 处理 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, 'yoga.db')


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
    """计算指定月份的成本明细"""
    cost_detail = {}
    for cat in ['房租', '工资', '水电煤', '其他']:
        cost_detail[cat] = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type='expense' AND category=? AND date >= ? AND date < ? AND user_id=?
        """, (cat, month_start, month_end, user_id)).fetchone()[0]
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
    """登录页面"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('login.html')
        
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['studio_name'] = user['studio_name']
            flash('登录成功', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('用户名或密码错误', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        studio_name = request.form.get('studio_name', '').strip()
        
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
            
            # 创建用户
            password_hash = generate_password_hash(password)
            db.execute(
                "INSERT INTO users (username, password_hash, studio_name) VALUES (?, ?, ?)",
                (username, password_hash, studio_name)
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
    today_str = datetime.now().strftime('%Y-%m-%d')
    with get_db() as db:
        rows = db.execute("""
            SELECT cr.id as class_id, cr.date, cr.time, cr.coach, cr.class_type, cr.notes,
                   m.id as member_id, m.name as member_name, m.card_type, m.price_per_class
            FROM class_records cr
            LEFT JOIN attendance a ON cr.id = a.class_record_id
            LEFT JOIN members m ON a.member_id = m.id
            WHERE cr.date = ? AND cr.user_id = ?
            ORDER BY cr.time DESC, cr.id DESC
        """, (today_str, user_id)).fetchall()

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
            'date': today_str,
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
                WHERE type='expense' AND category IN ('房租','工资','水电煤','其他') AND date >= ? AND date < ? AND user_id=?
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
        
        cost_detail = {}
        for cat in ['房租', '工资', '水电煤', '其他']:
            cost_detail[cat] = db.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM transactions 
                WHERE type='expense' AND category=? AND date >= ? AND date < ? AND user_id=?
            """, (cat, month_start, month_end, user_id)).fetchone()[0]
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


# ======================== 启动 ========================

def open_browser():
    """延迟打开浏览器"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')


if __name__ == '__main__':
    init_db()
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("\n" + "=" * 40)
    print("  🧘 瑜伽馆运营管理系统（多账户版）")
    print("  📍 访问地址: http://127.0.0.1:5000")
    print("  👤 首次使用请注册账户")
    print("  ⌨️  按 Ctrl+C 停止服务器")
    print("=" * 40 + "\n")
    
    app.run(host='127.0.0.1', port=5000, debug=False)