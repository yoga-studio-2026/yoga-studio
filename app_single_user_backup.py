#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""瑜伽馆运营管理系统 - Flask 后端"""

from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import sys
import webbrowser
import threading
from datetime import datetime, timedelta
import random

app = Flask(__name__)

# 处理 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, 'yoga.db')


# ======================== 辅助函数 ========================

def _month_range(today, offset=0):
    """计算月份范围，返回 (month_start, month_end, month_label)"""
    total_m = today.year * 12 + today.month - 1 - offset
    y = total_m // 12
    m_val = total_m % 12 + 1
    ms = f"{y}-{m_val:02d}-01"
    me = f"{y+1}-01-01" if m_val == 12 else f"{y}-{m_val+1:02d}-01"
    return ms, me, f"{y}-{m_val:02d}"


def _calc_cost_detail(db, month_start, month_end):
    """计算指定月份的成本明细"""
    cost_detail = {}
    for cat in ['房租', '工资', '水电煤', '其他']:
        cost_detail[cat] = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type='expense' AND category=? AND date >= ? AND date < ?
        """, (cat, month_start, month_end)).fetchone()[0]
    return cost_detail


def _calc_card_consume(db, month_start, month_end):
    """计算指定月份的消卡金额"""
    return db.execute("""
        SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
        JOIN class_records cr ON a.class_record_id = cr.id
        JOIN members m ON a.member_id = m.id
        WHERE cr.date >= ? AND cr.date < ?
    """, (month_start, month_end)).fetchone()[0]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS renewals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL DEFAULT 0,
                classes INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS class_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT DEFAULT '',
                coach TEXT DEFAULT '',
                class_type TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_record_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                FOREIGN KEY (class_record_id) REFERENCES class_records(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                type TEXT NOT NULL,
                category TEXT DEFAULT '',
                amount REAL NOT NULL,
                member_id INTEGER,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id)
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                class_date TEXT NOT NULL,
                class_time TEXT NOT NULL DEFAULT '',
                class_type TEXT DEFAULT '',
                coach TEXT DEFAULT '',
                status TEXT DEFAULT 'booked',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            );
        """)

        # 迁移：为现有表添加 time 字段（如果不存在）
        try:
            db.execute("ALTER TABLE class_records ADD COLUMN time TEXT DEFAULT ''")
        except:
            pass  # 字段已存在，忽略错误


def seed_data():
    """插入示例数据（仅当数据库为空时）"""
    # 使用标志文件优化启动速度
    seeded_flag = os.path.join(BASE_DIR, '.seeded')
    if os.path.exists(seeded_flag):
        return
    
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        if count > 0:
            # 已有数据，创建标志文件
            open(seeded_flag, 'w').close()
            return

        # --- 示例会员 ---
        today = datetime.now()
        members_data = [
            ("张丽", "13800138001", "私教", 6000, 20, 0, today - timedelta(days=60), today + timedelta(days=10)),  # 20节=10周
            ("王芳", "13800138002", "私教月卡", 3800, 12, 0, today - timedelta(days=30), today + timedelta(days=12)),  # 12节=6周
            ("李薇", "13800138003", "小班月卡", 880, 12, 0, today - timedelta(days=15), today + timedelta(days=27)),  # 12节=6周
            ("赵娜", "13800138004", "私教", 12000, 40, 0, today - timedelta(days=90), today + timedelta(days=50)),  # 40节=20周
            ("陈静", "13800138005", "小班", 2400, 10, 0, today - timedelta(days=7), today + timedelta(days=28)),  # 10节=5周
            ("刘洋", "13800138006", "小班月卡", 880, 12, 0, today - timedelta(days=20), today + timedelta(days=22)),  # 12节=6周
            ("周婷", "13800138007", "私教月卡", 3800, 12, 0, today - timedelta(days=45), today - timedelta(days=3)),  # 12节=6周
            ("吴霞", "13800138008", "小班", 2400, 10, 0, today - timedelta(days=80), today - timedelta(days=5)),  # 10节=5周
        ]

        # 模拟已上课时
        attended_map = {
            "张丽": 8, "王芳": 5, "李薇": 4, "赵娜": 15,
            "陈静": 3, "刘洋": 8, "周婷": 12, "吴霞": 6,
        }

        member_ids = []
        for m in members_data:
            name, phone, card_type, amount, total, _, signup, expiry = m
            attended = attended_map.get(name, 0)
            remaining = total - attended
            price = round(amount / total, 1) if total > 0 else 0
            db.execute("""INSERT INTO members
                (name, phone, card_type, card_amount, total_classes, price_per_class,
                 classes_attended, remaining_classes, signup_date, expiry_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, phone, card_type, amount, total, price,
                 attended, remaining, signup.strftime('%Y-%m-%d'),
                 expiry.strftime('%Y-%m-%d') if expiry else '', 'active'))
            member_ids.append(db.execute("SELECT last_insert_rowid()").fetchone()[0])

        # --- 示例上课记录 ---
        coaches = ["杨老师", "林老师", "陈老师", "黄老师", "唐老师"]
        class_types = ["流瑜伽", "哈他瑜伽", "阴瑜伽", "阿斯汤加", "理疗瑜伽", "空中瑜伽", "私教"]
        class_dates = []
        for i in range(35):
            d = today - timedelta(days=random.randint(0, 45))
            class_dates.append(d)

        records = []
        for i, d in enumerate(sorted(class_dates)):
            coach = random.choice(coaches)
            ct = random.choice(class_types)
            # 随机时间：9:00-20:00
            hour = random.randint(9, 20)
            time_str = f"{hour:02d}:{random.choice(['00','30'])}"
            db.execute("INSERT INTO class_records (date, time, coach, class_type) VALUES (?, ?, ?, ?)",
                       (d.strftime('%Y-%m-%d'), time_str, coach, ct))
            rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            # 随机2-6人参加
            attendees = random.sample(member_ids, min(random.randint(2, 6), len(member_ids)))
            for mid in attendees:
                db.execute("INSERT INTO attendance (class_record_id, member_id) VALUES (?, ?)", (rid, mid))

        # --- 示例交易流水 ---
        income_items = [
            ("张丽", 6000, "私教"), ("王芳", 3800, "私教月卡"), ("李薇", 880, "小班月卡"),
            ("赵娜", 12000, "私教"), ("陈静", 2400, "小班"), ("刘洋", 880, "小班月卡"),
            ("周婷", 3800, "私教月卡"), ("吴霞", 2400, "小班"),
        ]
        expense_items = [
            ("房租", 8000), ("水电", 1200), ("员工工资", 15000),
            ("保洁", 2000), ("耗材采购", 800), ("设备维护", 500),
            ("推广费", 1500), ("物业费", 600),
        ]

        # 近3个月每月收入
        for month_offset in range(3):
            month_start = today.replace(day=1) - timedelta(days=month_offset * 30)
            month_str = month_start.strftime('%Y-%m') + "-15"
            for name, amount, ctype in income_items:
                if random.random() < 0.6:
                    db.execute("INSERT INTO transactions (date, type, category, amount, notes) VALUES (?, 'income', ?, ?, ?)",
                               (month_str, "会费收入", amount, f"{name}办理{ctype}"))

        # 近3个月每月支出
        for month_offset in range(3):
            month_start = today.replace(day=1) - timedelta(days=month_offset * 30)
            month_str = month_start.strftime('%Y-%m') + "-05"
            for name, amount in expense_items:
                db.execute("INSERT INTO transactions (date, type, category, amount, notes) VALUES (?, 'expense', ?, ?, ?)",
                           (month_str, name, amount, f"{name}"))
        
        # 创建标志文件，下次启动跳过检查
        open(seeded_flag, 'w').close()


# ======================== 页面路由 ========================

@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/members')
def members():
    return render_template('members.html')


@app.route('/classes')
def class_records():
    return render_template('class_records.html')


@app.route('/finance')
def finance():
    return render_template('finance.html')


@app.route('/booking')
def booking():
    return render_template('booking.html')


# ======================== API: 仪表盘数据 ========================

@app.route('/api/dashboard')
def api_dashboard():
    with get_db() as db:
        today = datetime.now()
        ms, me, _ = _month_range(today, 0)

        # 本月收入（业绩）
        income = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ?",
            (ms, me)).fetchone()[0]

        # 本月成本
        cost_detail = _calc_cost_detail(db, ms, me)
        total_cost = sum(cost_detail.values())

        # 本月消卡
        card_consume = _calc_card_consume(db, ms, me)

        # 负债 = 未消耗课时总值
        liability = db.execute(
            "SELECT COALESCE(SUM(remaining_classes * price_per_class), 0) FROM members WHERE status='active'"
        ).fetchone()[0]

        # 活跃会员数
        active_members = db.execute("SELECT COUNT(*) FROM members WHERE status='active'").fetchone()[0]

        # 本月上课人次
        attend_count = db.execute("""
            SELECT COUNT(*) FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            WHERE cr.date >= ? AND cr.date < ?
        """, (ms, me)).fetchone()[0]

        # 累计现金流
        total_income = db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income'").fetchone()[0]
        total_expense = db.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense'").fetchone()[0]
        cash_balance = total_income - total_expense

        # 瑜伽馆评级
        studio_class = 'A' if cash_balance >= liability else 'B'

        # 近12个月趋势
        trend = []
        for i in range(11, -1, -1):
            tms, tme, label = _month_range(today, i)
            inc = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ?",
                (tms, tme)).fetchone()[0]
            cost = sum(_calc_cost_detail(db, tms, tme).values())
            card = _calc_card_consume(db, tms, tme)
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
            "SELECT card_type, COUNT(*) as count FROM members WHERE status='active' GROUP BY card_type"
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
        })


# ======================== API: 会员管理 ========================

@app.route('/api/members', methods=['GET'])
def api_members_list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    keyword = request.args.get('keyword', '')
    status = request.args.get('status', '')

    with get_db() as db:
        conditions = []
        params = []
        if keyword:
            conditions.append("(name LIKE ? OR phone LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        
        total = db.execute(f"SELECT COUNT(*) FROM members {where}", params).fetchone()[0]
        rows = db.execute(f"SELECT * FROM members {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [per_page, offset]).fetchall()

        members_list = [dict(r) for r in rows]
        
        # 计算当前页所有会员的剩余金额总计 + 购卡金额总计
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
def api_members_create():
    data = request.get_json()
    total = data.get('total_classes', 0)
    amount = data.get('card_amount', 0)
    price = round(amount / total, 1) if total > 0 else 0

    with get_db() as db:
        db.execute("""INSERT INTO members
            (name, phone, card_type, card_amount, total_classes, price_per_class,
             classes_attended, remaining_classes, signup_date, expiry_date, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'active')""",
            (data['name'], data.get('phone', ''), data.get('card_type', ''),
             amount, total, price, total, data.get('signup_date', datetime.now().strftime('%Y-%m-%d')),
             data.get('expiry_date') or _auto_expiry(data.get('signup_date', datetime.now().strftime('%Y-%m-%d')), total), data.get('notes', '')))
        mid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 如果购卡金额 > 0，自动生成交易记录
        if amount > 0:
            db.execute("INSERT INTO transactions (date, type, category, amount, member_id, notes) VALUES (?, 'income', '会费收入', ?, ?, ?)",
                       (data.get('signup_date', datetime.now().strftime('%Y-%m-%d')), amount, mid, f"{data['name']}办理{data.get('card_type','')}"))

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
def api_members_get(mid):
    with get_db() as db:
        member = db.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
        if not member:
            return jsonify({'error': '会员不存在'}), 404
        return jsonify(dict(member))


@app.route('/api/members/<int:mid>', methods=['PUT'])
def api_members_update(mid):
    data = request.get_json()
    total = data.get('total_classes', 0)
    amount = data.get('card_amount', 0)
    price = round(amount / total, 1) if total > 0 else 0
    attended = data.get('classes_attended', 0)
    remaining = total - attended

    with get_db() as db:
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
def api_members_delete(mid):
    with get_db() as db:
        # 检查会员是否有上课记录
        count = db.execute(
            "SELECT COUNT(*) FROM attendance WHERE member_id=?", (mid,)).fetchone()[0]
        if count > 0:
            return jsonify({'error': '该会员已有上课记录，无法删除。如需停用，请将会员状态改为"已过期"'}), 400
        db.execute("DELETE FROM members WHERE id=?", (mid,))
        return jsonify({'success': True})


@app.route('/api/members/<int:mid>/remaining', methods=['PATCH'])
def api_members_update_remaining(mid):
    """快速更新剩余课时（同时同步 classes_attended）"""
    data = request.get_json()
    remaining = data.get('remaining_classes')
    if remaining is None:
        return jsonify({'error': '缺少剩余课时参数'}), 400
    
    with get_db() as db:
        # 获取 total_classes，同步更新 classes_attended
        member = db.execute("SELECT total_classes FROM members WHERE id=?", (mid,)).fetchone()
        if not member:
            return jsonify({'error': '会员不存在'}), 404
        total = member['total_classes'] or 0
        attended = max(0, total - int(remaining))
        db.execute("UPDATE members SET remaining_classes = ?, classes_attended = ? WHERE id=?",
                   (int(remaining), attended, mid))
        return jsonify({'success': True})


@app.route('/api/members/<int:mid>/history')
def api_members_history(mid):
    with get_db() as db:
        rows = db.execute("""
            SELECT cr.date, cr.time, cr.coach, cr.class_type, cr.id as class_id
            FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            WHERE a.member_id = ?
            ORDER BY cr.date DESC, cr.time DESC
            LIMIT 100
        """, (mid,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 续卡记录 ========================
@app.route('/api/renewals', methods=['GET'])
def api_renewals_list():
    """查询续卡记录，member_id 参数可选"""
    member_id = request.args.get('member_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with get_db() as db:
        conditions = []
        params = []
        if member_id:
            conditions.append("r.member_id = ?")
            params.append(member_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = db.execute(f"SELECT COUNT(*) FROM renewals r {where}", params).fetchone()[0]
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
def api_renewals_create():
    """添加续卡记录，同时更新会员的课时和累计续卡金额/次数"""
    data = request.get_json()
    member_id = data.get('member_id')
    amount = data.get('amount', 0)
    classes = data.get('classes', 0)
    notes = data.get('notes', '')

    with get_db() as db:
        # 插入续卡记录
        db.execute("""
            INSERT INTO renewals (member_id, date, amount, classes, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (member_id, data.get('date', datetime.now().strftime('%Y-%m-%d')), amount, classes, notes))
        rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 更新会员表：累计课时、续卡次数、累计续卡金额
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
def api_renewals_delete(rid):
    """删除续卡记录，同时回滚会员的课时和累计数据"""
    with get_db() as db:
        # 先查询该记录的课时和金额
        row = db.execute("SELECT * FROM renewals WHERE id = ?", (rid,)).fetchone()
        if not row:
            return jsonify({'success': False, 'error': '记录不存在'})
        rec = dict(row)

        # 回滚会员数据
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
def api_renewals_by_member(mid):
    """查询某会员的所有续卡记录"""
    with get_db() as db:
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
def api_classes_list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM class_records").fetchone()[0]
        rows = db.execute("""
            SELECT cr.*, GROUP_CONCAT(m.name, '、') as member_names,
                   COUNT(a.id) as attend_count
            FROM class_records cr
            LEFT JOIN attendance a ON cr.id = a.class_record_id
            LEFT JOIN members m ON a.member_id = m.id
            GROUP BY cr.id
            ORDER BY cr.date DESC, cr.id DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()

        class_list = []
        for r in rows:
            item = dict(r)
            item['member_names'] = item['member_names'] or ''
            class_list.append(item)

        return jsonify({'classes': class_list, 'total': total, 'page': page, 'per_page': per_page})


@app.route('/api/classes', methods=['POST'])
def api_classes_create():
    data = request.get_json()
    member_ids = data.get('member_ids', [])

    with get_db() as db:
        db.execute("INSERT INTO class_records (date, time, coach, class_type, notes) VALUES (?, ?, ?, ?, ?)",
                   (data['date'], data.get('time', ''), data.get('coach', ''), 
                    data.get('class_type', ''), data.get('notes', '')))
        cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for mid in member_ids:
            db.execute("INSERT INTO attendance (class_record_id, member_id) VALUES (?, ?)", (cid, mid))
            # 扣减会员剩余课时
            db.execute("UPDATE members SET classes_attended = classes_attended + 1, remaining_classes = remaining_classes - 1 WHERE id = ? AND remaining_classes > 0",
                       (mid,))

        return jsonify({'success': True, 'id': cid})


@app.route('/api/classes/<int:cid>', methods=['DELETE'])
def api_classes_delete(cid):
    with get_db() as db:
        # 先恢复会员课时
        attendees = db.execute("SELECT member_id FROM attendance WHERE class_record_id=?", (cid,)).fetchall()
        for a in attendees:
            db.execute("UPDATE members SET classes_attended = MAX(0, classes_attended - 1), remaining_classes = remaining_classes + 1 WHERE id=?",
                       (a['member_id'],))
        db.execute("DELETE FROM class_records WHERE id=?", (cid,))
        return jsonify({'success': True})


@app.route('/api/classes/today')
def api_classes_today():
    """今日上课记录，含会员详情"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    with get_db() as db:
        rows = db.execute("""
            SELECT cr.id as class_id, cr.date, cr.time, cr.coach, cr.class_type, cr.notes,
                   m.id as member_id, m.name as member_name, m.card_type, m.price_per_class
            FROM class_records cr
            LEFT JOIN attendance a ON cr.id = a.class_record_id
            LEFT JOIN members m ON a.member_id = m.id
            WHERE cr.date = ?
            ORDER BY cr.time DESC, cr.id DESC
        """, (today_str,)).fetchall()

        # 按课程记录分组
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
def api_classes_update(cid):
    """更新单条上课记录（仅更新记录本身，不影响课时）"""
    data = request.get_json()
    with get_db() as db:
        db.execute("UPDATE class_records SET date=?, time=?, class_type=?, coach=?, notes=? WHERE id=?",
                   (data.get('date', ''), data.get('time', ''),
                    data.get('class_type', ''), data.get('coach', ''), 
                    data.get('notes', ''), cid))
        return jsonify({'success': True})


# ======================== API: 财务管理 ========================

@app.route('/api/transactions', methods=['GET'])
def api_transactions_list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    ttype = request.args.get('type', '')
    month = request.args.get('month', '')

    with get_db() as db:
        conditions = []
        params = []
        if ttype:
            conditions.append("t.type=?")
            params.append(ttype)
        if month:
            conditions.append("t.date LIKE ?")
            params.append(f"{month}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

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
def api_transactions_create():
    data = request.get_json()
    with get_db() as db:
        db.execute("INSERT INTO transactions (date, type, category, amount, notes, member_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (data['date'], data['type'], data.get('category', ''),
                    data['amount'], data.get('notes', ''), data.get('member_id') or None))
        tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({'success': True, 'id': tid})


@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def api_transactions_delete(tid):
    with get_db() as db:
        db.execute("DELETE FROM transactions WHERE id=?", (tid,))
        return jsonify({'success': True})


@app.route('/api/finance/summary')
def api_finance_summary():
    with get_db() as db:
        today = datetime.now()

        # 月度汇总
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
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income' AND date >= ? AND date < ?",
                (ms, me)).fetchone()[0]
            exp = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense' AND date >= ? AND date < ?",
                (ms, me)).fetchone()[0]
            
            # 计算月度成本（房租+工资+水电煤+其他）
            cost_rows = db.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM transactions 
                WHERE type='expense' AND category IN ('房租','工资','水电煤','其他') AND date >= ? AND date < ?
            """, (ms, me)).fetchone()[0]
            
            # 月度耗卡（消卡）
            card_rows = db.execute("""
                SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
                JOIN class_records cr ON a.class_record_id = cr.id
                JOIN members m ON a.member_id = m.id
                WHERE cr.date >= ? AND cr.date < ?
            """, (ms, me)).fetchone()[0]
            
            monthly.append({
                'month': f"{y}-{m_val:02d}",
                'income': inc,
                'expense': exp,
                'profit': inc - exp,
                'cost': cost_rows,
                'card_consumed': card_rows,
                'net_cash_flow': inc - cost_rows,      # 新现金流 = 业绩 - 成本
                'net_debt': inc - card_rows            # 新负债 = 业绩 - 消卡
            })

        # 本月成本明细
        month_start = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month.strftime('%Y-%m-%d')
        
        cost_detail = {}
        for cat in ['房租', '工资', '水电煤', '其他']:
            cost_detail[cat] = db.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM transactions 
                WHERE type='expense' AND category=? AND date >= ? AND date < ?
            """, (cat, month_start, month_end)).fetchone()[0]
        total_cost = sum(cost_detail.values())
        
        # 本月耗卡（消卡）
        card_consume = db.execute("""
            SELECT COALESCE(SUM(m.price_per_class), 0) FROM attendance a
            JOIN class_records cr ON a.class_record_id = cr.id
            JOIN members m ON a.member_id = m.id
            WHERE cr.date >= ? AND cr.date < ?
        """, (month_start, month_end)).fetchone()[0]

        # 本月收入（业绩）
        month_income = db.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type='income' AND date >= ? AND date < ?
        """, (month_start, month_end)).fetchone()[0]
        
        # 负债 = 已收钱但未消耗的课时总值
        liability = db.execute(
            "SELECT COALESCE(SUM(remaining_classes * price_per_class), 0) FROM members WHERE status='active'"
        ).fetchone()[0]

        # 总资产 + 初始现金流
        initial_cf = float(db.execute(
            "SELECT COALESCE(CAST(value AS REAL), 0) FROM config WHERE key='initial_cash_flow'"
        ).fetchone()[0])
        total_income = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='income'").fetchone()[0]
        total_expense = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='expense'").fetchone()[0]

        return jsonify({
            'monthly': monthly,
            'card_consumption': card_consume,
            'cost_detail': cost_detail,
            'total_cost': total_cost,
            'month_income': month_income,
            'profit': card_consume - total_cost,          # 利润 = 消卡 - 成本
            'net_cash_flow': month_income - total_cost,    # 新增现金流 = 业绩 - 成本
            'net_debt': month_income - card_consume,              # 新增负债 = 业绩 - 消卡
            'cash_balance': total_income - total_expense + initial_cf,  # 现金流 = 累计收入 - 累计支出 + 初始现金流
            'initial_cash_flow': initial_cf,                        # 初始现金流
            'liability': liability,                                   # 负债 = 未消课时总值
            'total_income': total_income,
            'total_expense': total_expense,
            'total_profit': total_income - total_expense,
            'studio_class': 'A' if (total_income - total_expense + initial_cf) >= liability else 'B',
        })

@app.route('/api/finance/config', methods=['POST'])
def api_finance_config():
    data = request.get_json()
    key = data.get('key', '')
    value = str(data.get('value', '0'))
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'key': key, 'value': value})

@app.route('/api/members/all')
def api_members_all():
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, phone, card_type, remaining_classes, status FROM members WHERE status='active' ORDER BY name"
        ).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== API: 预约管理 ========================

@app.route('/api/bookings', methods=['GET'])
def api_bookings_list():
    """获取预约列表，支持日期筛选和状态筛选"""
    date_filter = request.args.get('date', '')
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = 20

    conditions = []
    params = []
    if date_filter:
        conditions.append('b.class_date = ?')
        params.append(date_filter)
    if status:
        conditions.append('b.status = ?')
        params.append(status)

    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''

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
def api_bookings_create():
    """创建预约"""
    data = request.get_json()
    member_id = data.get('member_id')
    if not member_id:
        return jsonify({'error': '请选择会员'}), 400

    with get_db() as db:
        # 检查是否重复预约
        existing = db.execute(
            "SELECT id FROM bookings WHERE member_id=? AND class_date=? AND class_time=? AND status='booked'",
            (member_id, data['class_date'], data.get('class_time', ''))
        ).fetchone()
        if existing:
            return jsonify({'error': '该会员此时段已有预约'}), 400

        db.execute("""INSERT INTO bookings
            (member_id, class_date, class_time, class_type, coach, status, notes)
            VALUES (?, ?, ?, ?, ?, 'booked', ?)""",
            (member_id, data['class_date'], data.get('class_time', ''),
             data.get('class_type', ''), data.get('coach', ''), data.get('notes', '')))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['PUT'])
def api_bookings_update(bid):
    """更新预约状态（签到/取消）"""
    data = request.get_json()
    with get_db() as db:
        db.execute("UPDATE bookings SET status=?, notes=? WHERE id=?",
                   (data.get('status', 'booked'), data.get('notes', ''), bid))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['DELETE'])
def api_bookings_delete(bid):
    """删除预约"""
    with get_db() as db:
        db.execute("DELETE FROM bookings WHERE id=?", (bid,))
        return jsonify({'success': True})


@app.route('/api/bookings/<int:bid>', methods=['GET'])
def api_bookings_get(bid):
    """获取单条预约详情"""
    with get_db() as db:
        row = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({'error': '预约不存在'}), 404


@app.route('/api/bookings/<int:bid>/attend', methods=['POST'])
def api_bookings_attend(bid):
    """签到：将预约标记为已上课，扣减课时，生成上课记录"""
    with get_db() as db:
        # 获取预约信息
        booking = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if not booking:
            return jsonify({'error': '预约不存在'}), 404
        
        if booking['status'] != 'booked':
            return jsonify({'error': '该预约已处理'}), 400
        
        member_id = booking['member_id']
        
        # 检查会员剩余课时
        member = db.execute("SELECT remaining_classes FROM members WHERE id=?", (member_id,)).fetchone()
        if not member or member['remaining_classes'] <= 0:
            return jsonify({'error': '会员课时不足'}), 400
        
        # 创建上课记录
        db.execute("""INSERT INTO class_records (date, time, coach, class_type, notes)
                     VALUES (?, ?, ?, ?, ?)""",
                   (booking['class_date'], booking['class_time'],
                    booking['coach'], booking['class_type'],
                    f"预约签到 - {booking['notes'] or ''}"))
        record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        # 关联会员到上课记录
        db.execute("INSERT INTO attendance (class_record_id, member_id) VALUES (?, ?)",
                   (record_id, member_id))
        
        # 扣减会员课时
        db.execute("""UPDATE members 
                     SET classes_attended = classes_attended + 1,
                         remaining_classes = remaining_classes - 1
                     WHERE id=?""", (member_id,))
        
        # 更新预约状态为已上课
        db.execute("UPDATE bookings SET status='attended' WHERE id=?", (bid,))
        
        return jsonify({'success': True, 'record_id': record_id})


@app.route('/api/bookings/date/<date_str>')
def api_bookings_by_date(date_str):
    """获取某天的所有预约（给日历视图用）"""
    with get_db() as db:
        rows = db.execute("""
            SELECT b.id, b.class_date, b.class_time, b.class_type, b.coach, b.status,
                   m.id as member_id, m.name as member_name, m.card_type
            FROM bookings b
            LEFT JOIN members m ON b.member_id = m.id
            WHERE b.class_date = ? AND b.status = 'booked'
            ORDER BY b.class_time
        """, (date_str,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ======================== 启动 ========================

def open_browser():
    """延迟打开浏览器"""
    import time
    time.sleep(1.5)  # 等待服务器启动
    webbrowser.open('http://localhost:5000')


if __name__ == '__main__':
    init_db()
    seed_data()
    
    # 自动打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("\n" + "=" * 40)
    print("  🧘 瑜伽馆运营管理系统")
    print("  📍 访问地址: http://127.0.0.1:5000")
    print("  ⌨️  按 Ctrl+C 停止服务器")
    print("=" * 40 + "\n")
    
    app.run(host='127.0.0.1', port=5000, debug=False)
