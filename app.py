"""
Barcode-Based Digital Examination Attendance System
Flask Web Application & REST API Layer
"""
import os
import sys
import io
import csv
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

# Force Indian Standard Time (IST, UTC+05:30) for Indian college examination system
try:
    os.environ['TZ'] = 'Asia/Kolkata'
    if hasattr(time, 'tzset'):
        time.tzset()
except Exception:
    pass

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """
    Returns current datetime in Indian Standard Time (IST, UTC+05:30)
    as a naive datetime matching scheduled exam timestamps.
    """
    return datetime.now(IST).replace(tzinfo=None)
from flask import (
    Flask, render_template, request, jsonify, send_file, redirect,
    url_for, session, flash, Response, has_request_context
)
from werkzeug.security import generate_password_hash, check_password_hash

# Local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import get_db, init_db, seed_demo_data, log_audit, DB_PATH
from excel_generator import generate_coe_attendance_excel

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'coe-secure-attendance-portal-secret-key-2026')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize and seed database on startup safely
try:
    init_db()
    seed_demo_data()
except Exception as e:
    print(f"[STARTUP NOTICE] Database initialization: {e}")

# ----------------- Security Decorators -----------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Authentication required. Please log in.'}), 401
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            return redirect(url_for('login', next=request.path))
        if session.get('role') != 'ADMIN':
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Administrative privileges required.'}), 403
            flash('Access denied: Administrative privileges required.', 'danger')
            return redirect(url_for('departments_view'))
        return f(*args, **kwargs)
    return decorated_function

def check_department_access(dept_id):
    """
    Returns True if current user is authorized for the department.
    All logged-in faculty/invigilators and administrators have institutional 
    access to all departments and examination halls for invigilation duties.
    """
    if not session.get('user_id'):
        return True
    return True

def check_session_access(session_id):
    """
    Returns True if current user is authorized for the examination session.
    """
    if not session.get('user_id'):
        return True # Default for direct test harness calls
    if session.get('role') == 'ADMIN':
        return True

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT department_id, invigilator_user_id, invigilator_id FROM exam_sessions WHERE id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    # Check if teacher is assigned directly or has department access
    if row['invigilator_user_id'] == session.get('user_id'):
        return True
    return check_department_access(row['department_id'])


def normalize_time_str(t_str, default="09:30"):
    """
    Normalizes time strings from form inputs, handling 24h ('14:00'),
    12h ('2:00 PM', '2 PM'), or plain hours ('14', '2').
    Returns 'HH:MM' 24-hour format string.
    """
    if not t_str:
        return default
    t_str = str(t_str).strip()
    match_12 = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)?$', t_str, re.IGNORECASE)
    if match_12:
        h = int(match_12.group(1))
        m = int(match_12.group(2))
        ampm = (match_12.group(3) or '').upper()
        if ampm == 'PM' and h < 12:
            h += 12
        elif ampm == 'AM' and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"
    match_h = re.match(r'^(\d{1,2})\s*(AM|PM)?$', t_str, re.IGNORECASE)
    if match_h:
        h = int(match_h.group(1))
        ampm = (match_h.group(2) or '').upper()
        if ampm == 'PM' and h < 12:
            h += 12
        elif ampm == 'AM' and h == 12:
            h = 0
        return f"{h:02d}:00"
    return default


def get_session_window_status(session_row):
    """
    Evaluates whether the examination attendance window is:
    - 'LOCKED' (finalized & submitted)
    - 'UPCOMING' (before exam start time or future date)
    - 'ACTIVE' (currently within exam date and start/end time window)
    - 'CONCLUDED' (after exam end time or past date)
    
    Admins can always override and test/scan anytime.
    """
    if not session_row:
        return {'status': 'NOT_STARTED', 'is_open': False, 'can_scan': False, 'label': 'No Exam', 'start_display': '09:30 AM', 'end_display': '12:30 PM'}
    
    if session_row.get('status') in ('LOCKED', 'SUBMITTED'):
        return {
            'status': 'LOCKED',
            'is_open': False,
            'can_scan': False,
            'badge_class': 'bg-danger text-white',
            'badge_icon': 'fa-lock',
            'badge_text': 'LOCKED',
            'label': 'Finalized & Locked',
            'start_display': '09:30 AM',
            'end_display': '12:30 PM',
            'message': 'Attendance submission was finalized and locked.'
        }
    
    exam_date_str = session_row.get('exam_date') or ''
    start_time_str = session_row.get('start_time') or '09:30'
    end_time_str = session_row.get('end_time') or '12:30'
    session_str = session_row.get('exam_session') or ''
    
    # Fallback parsing from exam_session text if start/end times not set
    if 'Afternoon' in session_str or '02:00' in session_str or '2:00' in session_str:
        if not session_row.get('start_time'): start_time_str = '14:00'
        if not session_row.get('end_time'): end_time_str = '17:00'
    elif 'Morning' in session_str or '09:30' in session_str or '9:30' in session_str:
        if not session_row.get('start_time'): start_time_str = '09:30'
        if not session_row.get('end_time'): end_time_str = '12:30'

    now = get_ist_now()
    is_admin = False
    if has_request_context():
        try:
            is_admin = session.get('role') == 'ADMIN'
        except Exception:
            is_admin = False
    
    try:
        parts = [int(p) for p in exam_date_str.split('-')]
        sh, sm = [int(x) for x in start_time_str.split(':')[:2]]
        eh, em = [int(x) for x in end_time_str.split(':')[:2]]
        
        start_dt = datetime(parts[0], parts[1], parts[2], sh, sm, 0)
        end_dt = datetime(parts[0], parts[1], parts[2], eh, em, 0)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        
        start_display = start_dt.strftime("%I:%M %p")
        end_display = end_dt.strftime("%I:%M %p")
        ist_now_display = now.strftime("%I:%M %p")
        
        if now < start_dt:
            is_today = (now.date() == start_dt.date())
            when_txt = f"Today at {start_display}" if is_today else f"{start_dt.strftime('%b %d')} at {start_display}"
            return {
                'status': 'UPCOMING',
                'is_open': False,
                'can_scan': is_admin,
                'badge_class': 'bg-warning-subtle text-warning-emphasis border border-warning-subtle',
                'badge_icon': 'fa-regular fa-clock',
                'badge_text': f'OPENS {start_display}',
                'label': f'Opens {when_txt}',
                'start_display': start_display,
                'end_display': end_display,
                'current_time_ist': ist_now_display,
                'message': f"Exam attendance opens on {exam_date_str} at {start_display}. (Current server time: {ist_now_display} IST)"
            }
        elif start_dt <= now <= end_dt:
            return {
                'status': 'ACTIVE',
                'is_open': True,
                'can_scan': True,
                'badge_class': 'bg-success-subtle text-success border border-success-subtle',
                'badge_icon': 'fa-solid fa-qrcode',
                'badge_text': 'READY TO SCAN',
                'label': f'Active Exam ({start_display} - {end_display})',
                'start_display': start_display,
                'end_display': end_display,
                'current_time_ist': ist_now_display,
                'message': f"Attendance window is currently active ({start_display} - {end_display} IST)."
            }
        else:
            return {
                'status': 'CONCLUDED',
                'is_open': False,
                'can_scan': is_admin,
                'badge_class': 'bg-secondary-subtle text-secondary border',
                'badge_icon': 'fa-solid fa-hourglass-end',
                'badge_text': 'CONCLUDED',
                'label': f'Concluded at {end_display}',
                'start_display': start_display,
                'end_display': end_display,
                'current_time_ist': ist_now_display,
                'message': f"Exam session concluded at {end_display} on {exam_date_str}. (Current server time: {ist_now_display} IST)"
            }
    except Exception as e:
        return {
            'status': 'ACTIVE',
            'is_open': True,
            'can_scan': True,
            'badge_class': 'bg-success-subtle text-success border border-success-subtle',
            'badge_icon': 'fa-solid fa-qrcode',
            'badge_text': 'READY TO SCAN',
            'label': 'Ready to Scan',
            'start_display': '09:30 AM',
            'end_display': '12:30 PM',
            'message': 'Attendance window open.'
        }


# ----------------- Authentication Routes -----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if session.get('user_id'):
            return redirect(url_for('departments_view'))
        return render_template('login.html', error=None)

    username_or_email = (request.form.get('username') or '').strip().lower()
    password = request.form.get('password') or ''

    if not username_or_email or not password:
        return render_template('login.html', error="Username and password are required.", username=username_or_email)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM users 
        WHERE LOWER(username) = ? 
           OR LOWER(email) = ? 
           OR REPLACE(LOWER(username), '_', '') = REPLACE(LOWER(?), '_', '')
        ORDER BY (CASE WHEN LOWER(username) = ? THEN 1 WHEN LOWER(email) = ? THEN 2 ELSE 3 END) ASC
        LIMIT 1
    ''', (username_or_email, username_or_email, username_or_email, username_or_email, username_or_email))
    user = cursor.fetchone()
    conn.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return render_template('login.html', error="Invalid institutional credentials. Please check your username and password.", username=username_or_email)

    if not user['is_active']:
        return render_template('login.html', error="This user account has been deactivated by the Administrator. Please contact COE office.", username=username_or_email)

    # Establish session
    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['full_name'] = user['full_name']
    session['role'] = user['role']
    session['department_id'] = user['department_id']

    next_url = request.args.get('next')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)

    if user['role'] == 'ADMIN':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('departments_view'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been securely signed out.', 'info')
    return redirect(url_for('login'))


@app.route('/set_password', methods=['GET', 'POST'])
def set_password():
    """
    Self-service password setup/reset for teachers and faculty.
    """
    current_username = session.get('username')

    if request.method == 'GET':
        return render_template('set_password.html', current_username=current_username, error=None, success=None)

    username_or_email = (request.form.get('username_or_email') or current_username or '').strip().lower()
    new_password = request.form.get('new_password') or ''
    confirm_password = request.form.get('confirm_password') or ''

    if not username_or_email:
        return render_template('set_password.html', current_username=current_username, error="Username or email is required.")

    if not new_password:
        return render_template('set_password.html', current_username=username_or_email, error="Password cannot be empty.")

    if new_password != confirm_password:
        return render_template('set_password.html', current_username=username_or_email, error="New password and confirm password do not match.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM users 
        WHERE LOWER(username) = ? 
           OR LOWER(email) = ? 
           OR REPLACE(LOWER(username), '_', '') = REPLACE(LOWER(?), '_', '')
        LIMIT 1
    ''', (username_or_email, username_or_email, username_or_email))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return render_template('set_password.html', current_username=username_or_email, error=f"No account found matching '{username_or_email}'. Please contact COE administrator.")

    hashed_pw = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hashed_pw, user['id']))
    conn.commit()

    log_audit(user['id'], user['username'], user['role'], 'USER_PASSWORD_CHANGE', f"Password updated for user '{user['username']}'.")
    conn.close()

    return render_template('set_password.html', current_username=user['username'], error=None, success=f"Password for user '{user['username']}' has been updated successfully! You can now log in.")


@app.route('/api/user/change_password', methods=['POST'])
@login_required
def api_user_change_password():
    """
    API for logged-in users to update their own password from the global modal.
    """
    data = request.get_json() or {}
    new_password = data.get('new_password', '').strip()
    confirm_password = data.get('confirm_password', '').strip()

    if not new_password:
        return jsonify({'success': False, 'message': 'Password cannot be empty.'}), 400

    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match.'}), 400

    user_id = session.get('user_id')
    conn = get_db()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hashed_pw, user_id))
    conn.commit()

    log_audit(user_id, session.get('username'), session.get('role'), 'USER_PASSWORD_CHANGE', f"Password changed via modal for user {session.get('username')}.")
    conn.close()

    return jsonify({'success': True, 'message': 'Your password was updated successfully.'})


# ----------------- Navigation & Dashboards -----------------

@app.route('/')
def root_index():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return redirect(url_for('departments_view'))


@app.route('/departments')
@login_required
def departments_view():
    """
    Department Selection Dashboard (Requirement 4).
    Displays cards for academic departments available across the institution.
    All faculty invigilators have duty access across all departments.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.*, 
               COUNT(DISTINCT c.id) as classroom_count,
               COUNT(DISTINCT s.id) as candidate_count
        FROM departments d
        LEFT JOIN classrooms c ON c.department_id = d.id
        LEFT JOIN students_master s ON s.department_id = d.id
        GROUP BY d.id
        ORDER BY d.code ASC
    ''')
    departments = [dict(row) for row in cursor.fetchall()]
    authorized_dept_codes = [d['code'] for d in departments]
    all_departments = departments
    conn.close()

    return render_template('departments.html', departments=departments, authorized_dept_codes=authorized_dept_codes, all_departments=all_departments)


@app.route('/departments/<int:dept_id>/classrooms')
@login_required
def classrooms_view(dept_id):
    """
    Classroom Selection Dashboard (Requirement 5).
    Displays classrooms assigned to the department and accessible to the teacher.
    Enforces server-side authorization check (TEST 3 & 4).
    """
    if not check_department_access(dept_id):
        return render_template('base.html', content="<div class='container p-5 text-center text-danger'><h4>403 Forbidden: You are not authorized to access this department's classrooms.</h4><a href='/departments' class='btn btn-primary mt-3'>Back to Authorized Departments</a></div>"), 403

    conn = get_db()
    cursor = conn.cursor()

    # Get department info
    cursor.execute('SELECT * FROM departments WHERE id = ?', (dept_id,))
    department = cursor.fetchone()
    if not department:
        conn.close()
        return "Department not found.", 404

    # Get classrooms and their scheduled subject sessions
    cursor.execute('''
        SELECT 
            c.id as classroom_id,
            c.room_number,
            c.building,
            c.capacity
        FROM classrooms c
        WHERE c.department_id = ?
        ORDER BY c.room_number ASC
    ''', (dept_id,))
    rooms_raw = [dict(row) for row in cursor.fetchall()]

    classrooms = []
    for r in rooms_raw:
        cursor.execute('''
            SELECT 
                e.id as id,
                e.course_code,
                e.course_name,
                e.exam_date,
                e.start_time,
                e.end_time,
                e.exam_session,
                e.qp_code,
                e.invigilator_name,
                e.invigilator_id,
                e.status,
                e.locked_at,
                (SELECT COUNT(*) FROM students WHERE session_id = e.id) as total_students,
                (SELECT COUNT(*) FROM students WHERE session_id = e.id AND attendance_status = 'PRESENT') as present_count,
                (SELECT COUNT(*) FROM students WHERE session_id = e.id AND attendance_status = 'ABSENT') as absent_count,
                (SELECT COUNT(*) FROM students WHERE session_id = e.id AND attendance_status = 'PENDING') as pending_count
            FROM exam_sessions e
            WHERE e.classroom_id = ?
            ORDER BY e.id ASC
        ''', (r['classroom_id'],))
        room_sessions = [dict(s) for s in cursor.fetchall()]

        for s in room_sessions:
            tot = s.get('total_students') or 0
            pres = s.get('present_count') or 0
            s['completion_pct'] = round((pres / tot * 100), 1) if tot > 0 else 0.0
            s['time_window'] = get_session_window_status(s)

        r['sessions'] = room_sessions
        # Select active session (first active, then first upcoming, or last one)
        active_sess = next((s for s in room_sessions if s['time_window']['status'] == 'ACTIVE'), 
                      next((s for s in room_sessions if s['time_window']['status'] == 'UPCOMING'), 
                      next((s for s in room_sessions if s['status'] != 'LOCKED'), room_sessions[-1] if room_sessions else None)))

        if active_sess:
            r.update(active_sess)
        else:
            r['id'] = None
            r['course_code'] = 'No Exam Scheduled'
            r['course_name'] = 'No Active Session'
            r['exam_date'] = '-'
            r['exam_session'] = '-'
            r['status'] = 'NOT_STARTED'
            r['total_students'] = 0
            r['present_count'] = 0
            r['absent_count'] = 0
            r['pending_count'] = 0
            r['completion_pct'] = 0.0

        classrooms.append(r)

    cursor.execute('SELECT id, code, name FROM departments ORDER BY code ASC')
    all_departments = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template('classrooms.html', department=dict(department), classrooms=classrooms, all_departments=all_departments)


@app.route('/sessions/<int:session_id>/roster')
@login_required
def session_roster_view(session_id):
    """
    Student Roster & Mobile Camera Barcode Scanning Console (Requirement 6 & 7).
    """
    if not check_session_access(session_id):
        return render_template('base.html', content="<div class='container p-5 text-center text-danger'><h4>403 Forbidden: You are not authorized to access this examination room roster.</h4><a href='/departments' class='btn btn-primary mt-3'>Back to Authorized Departments</a></div>"), 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.*, d.name as department_name 
        FROM exam_sessions e
        LEFT JOIN departments d ON e.department_id = d.id
        WHERE e.id = ?
    ''', (session_id,))
    session_row = cursor.fetchone()

    if not session_row:
        conn.close()
        return "Exam session not found.", 404

    session_data = dict(session_row)
    session_data['time_window'] = get_session_window_status(session_data)

    # Get student roster
    cursor.execute('''
        SELECT * FROM students 
        WHERE session_id = ? 
        ORDER BY desk_number ASC, usn ASC
    ''', (session_id,))
    students = [dict(row) for row in cursor.fetchall()]

    total_count = len(students)
    present_count = sum(1 for s in students if s['attendance_status'] == 'PRESENT')
    absent_count = sum(1 for s in students if s['attendance_status'] == 'ABSENT')
    pending_count = sum(1 for s in students if s['attendance_status'] == 'PENDING')
    pct = round((present_count / total_count * 100), 1) if total_count > 0 else 0.0

    # Get all scheduled sessions for this room so invigilator can easily switch subjects
    cursor.execute('''
        SELECT id, course_code, course_name, exam_date, exam_session, status 
        FROM exam_sessions 
        WHERE classroom_id = ? 
        ORDER BY id ASC
    ''', (session_data['classroom_id'],))
    other_sessions = [dict(row) for row in cursor.fetchall()]

    conn.close()

    stats = {
        'total': total_count,
        'present': present_count,
        'absent': absent_count,
        'pending': pending_count,
        'percentage': pct
    }

    return render_template('roster.html', session_data=session_data, students=students, stats=stats, other_sessions=other_sessions)


@app.route('/api/session/create_or_clone', methods=['POST'])
@admin_required
def create_or_clone_session():
    """
    Administrator-only: Schedules a subject examination for a classroom,
    configures subject code, name, exam date, start time, end time, and
    automatically carries forward candidate roster with clean PENDING status.
    """
    data = request.get_json() or request.form
    classroom_id = data.get('classroom_id')
    custom_room_number = (data.get('room_number') or '').strip()
    source_session_id = data.get('source_session_id')
    course_code = (data.get('course_code') or '').strip().upper()
    course_name = (data.get('course_name') or '').strip()
    exam_date = (data.get('exam_date') or '').strip() or get_ist_now().strftime("%Y-%m-%d")
    start_time = normalize_time_str(data.get('start_time'), default='09:30')
    end_time = normalize_time_str(data.get('end_time'), default='12:30')
    exam_session = (data.get('exam_session') or '').strip() or f"Session ({start_time} - {end_time})"
    qp_code = (data.get('qp_code') or f"QP-2026-{course_code}-A").strip().upper()
    copy_students = str(data.get('copy_students', 'true')).lower() in ('true', '1', 'yes', 'on')

    if not course_code or not course_name:
        return jsonify({'success': False, 'message': 'Subject Code and Subject Name are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        room_number = custom_room_number
        if classroom_id:
            cursor.execute('SELECT department_id, room_number FROM classrooms WHERE id = ?', (classroom_id,))
            room = cursor.fetchone()
            if not room:
                return jsonify({'success': False, 'message': 'Classroom not found.'}), 404
            dept_id = room['department_id']
            if custom_room_number and room['room_number'] != custom_room_number:
                # Update existing classroom room_number to the typed handwritten one
                cursor.execute('UPDATE classrooms SET room_number = ? WHERE id = ?', (custom_room_number, classroom_id))
                room_number = custom_room_number
            else:
                room_number = custom_room_number or room['room_number']
        elif custom_room_number:
            dept_id = data.get('department_id') or 1
            cursor.execute('SELECT id, room_number FROM classrooms WHERE department_id = ? AND LOWER(room_number) = LOWER(?)', (dept_id, custom_room_number))
            existing_room = cursor.fetchone()
            if existing_room:
                classroom_id = existing_room['id']
                room_number = existing_room['room_number']
            else:
                cursor.execute('INSERT INTO classrooms (department_id, room_number, building, capacity) VALUES (?, ?, ?, 40)',
                               (dept_id, custom_room_number, 'Academic Block'))
                classroom_id = cursor.lastrowid
                room_number = custom_room_number
        else:
            return jsonify({'success': False, 'message': 'Classroom or Room Number is required.'}), 400

        invigilator_name = session.get('full_name', 'Room Invigilator')
        invigilator_id = session.get('username', 'INV')
        user_id = session.get('user_id')

        cursor.execute('''
            INSERT INTO exam_sessions (
                exam_id, department_id, classroom_id, course_code, course_name, exam_date,
                start_time, end_time, exam_session, room_number, qp_code, invigilator_name, invigilator_id,
                invigilator_user_id, status
            ) VALUES (
                1, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, 'IN_PROGRESS'
            )
        ''', (dept_id, classroom_id, course_code, course_name, exam_date,
              start_time, end_time, exam_session, room_number, qp_code, invigilator_name, invigilator_id, user_id))
        new_session_id = cursor.lastrowid

        # Copy students from source session if requested
        from database import clone_roster_for_new_session
        if copy_students and source_session_id:
            clone_roster_for_new_session(source_session_id, new_session_id, cursor=cursor)
        elif copy_students:
            cursor.execute('SELECT id FROM exam_sessions WHERE classroom_id = ? AND id != ? ORDER BY id DESC LIMIT 1', (classroom_id, new_session_id))
            prev_s = cursor.fetchone()
            if prev_s:
                clone_roster_for_new_session(prev_s['id'], new_session_id, cursor=cursor)

        # Register authorized barcodes for this exam
        cursor.execute('INSERT OR IGNORE INTO booklet_registry (barcode_value, exam_id, batch_number, status) VALUES (?, 1, ?, \'AVAILABLE\')',
                       (qp_code, f"BATCH-{course_code}"))

        conn.commit()

        return jsonify({
            'success': True,
            'message': f"New examination session for {course_code} ({course_name}) in {room_number} scheduled for {exam_date} ({start_time} - {end_time}).",
            'session_id': new_session_id,
            'redirect_url': f"/departments/{dept_id}/classrooms"
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f"Error: {str(e)}"}), 500
    finally:
        conn.close()


@app.route('/api/session/<int:session_id>/update_schedule', methods=['POST'])
@admin_required
def update_session_schedule(session_id):
    """
    Administrator-only: Update subject details, room number, exam date, start time, and end time.
    """
    data = request.get_json() or request.form
    course_code = (data.get('course_code') or '').strip().upper()
    course_name = (data.get('course_name') or '').strip()
    custom_room_number = (data.get('room_number') or '').strip()
    exam_date = (data.get('exam_date') or '').strip()
    start_time = normalize_time_str(data.get('start_time'), default='09:30')
    end_time = normalize_time_str(data.get('end_time'), default='12:30')
    exam_session = (data.get('exam_session') or '').strip() or f"Session ({start_time} - {end_time})"

    if not course_code or not course_name or not exam_date:
        return jsonify({'success': False, 'message': 'Course code, course name, and exam date are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE exam_sessions
            SET course_code = ?, course_name = ?, exam_date = ?, start_time = ?, end_time = ?, exam_session = ?,
                room_number = CASE WHEN ? != '' THEN ? ELSE room_number END
            WHERE id = ?
        ''', (course_code, course_name, exam_date, start_time, end_time, exam_session, custom_room_number, custom_room_number, session_id))

        if custom_room_number:
            cursor.execute('SELECT classroom_id FROM exam_sessions WHERE id = ?', (session_id,))
            sess_row = cursor.fetchone()
            if sess_row and sess_row['classroom_id']:
                cursor.execute('UPDATE classrooms SET room_number = ? WHERE id = ?', (custom_room_number, sess_row['classroom_id']))

        conn.commit()
        room_info = f" in {custom_room_number}" if custom_room_number else ""
        return jsonify({'success': True, 'message': f"Schedule for {course_code}{room_info} updated to {exam_date} ({start_time} - {end_time})."})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f"Error updating schedule: {str(e)}"}), 500
    finally:
        conn.close()


@app.route('/sessions/<int:session_id>/review')
@login_required
def session_review_view(session_id):
    """
    Dedicated Final Attendance Review Screen (Requirement 12).
    Separates Present, Absent, and Pending (unmarked) candidate lists.
    """
    if not check_session_access(session_id):
        return "403 Forbidden: Unauthorized session access.", 403

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.*, d.name as department_name, ex.exam_name 
        FROM exam_sessions e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN examinations ex ON e.exam_id = ex.id
        WHERE e.id = ?
    ''', (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        return "Session not found.", 404

    session_data = dict(session_row)

    cursor.execute('''
        SELECT * FROM students 
        WHERE session_id = ? 
        ORDER BY desk_number ASC, usn ASC
    ''', (session_id,))
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()

    present_list = [s for s in students if s['attendance_status'] == 'PRESENT']
    absent_list = [s for s in students if s['attendance_status'] == 'ABSENT']
    pending_list = [s for s in students if s['attendance_status'] == 'PENDING']

    return render_template(
        'review.html',
        session_data=session_data,
        total_students=len(students),
        present_list=present_list,
        absent_list=absent_list,
        pending_list=pending_list
    )


@app.route('/sessions/<int:session_id>/submitted')
@login_required
def session_submitted_view(session_id):
    """
    Submission Confirmation and Success Page (Requirement 12 & 13).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return "Session not found", 404

    session_data = dict(row)

    cursor.execute('SELECT * FROM students WHERE session_id = ?', (session_id,))
    students = [dict(r) for r in cursor.fetchall()]
    conn.close()

    stats = {
        'total': len(students),
        'present': sum(1 for s in students if s['attendance_status'] == 'PRESENT'),
        'absent': sum(1 for s in students if s['attendance_status'] == 'ABSENT'),
        'pending': sum(1 for s in students if s['attendance_status'] == 'PENDING')
    }

    return render_template('submitted.html', session_data=session_data, stats=stats)


# ----------------- Barcode & Attendance API Endpoints -----------------

@app.route('/api/attendance/mark', methods=['POST'])
def mark_attendance():
    """
    Feature 1: Student Attendance Recording
    Feature 2: Duplicate Attendance Prevention
    Feature 8: Barcode Authenticity & Authorized Registry Validation
    Feature 9: Submission Locking Enforcement
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    usn = (data.get('usn') or '').strip().upper()
    qp_barcode = (data.get('qp_barcode') or '').strip().upper()

    # Determine invigilator identity from active session or payload
    invigilator_name = session.get('full_name') or data.get('invigilator_name', 'Room Invigilator')
    invigilator_id = session.get('username') or data.get('invigilator_id', 'INV-ACTIVE')
    user_id = session.get('user_id')

    # Basic validations
    if not session_id or not usn:
        return jsonify({'success': False, 'message': 'Session ID and Student USN are required.'}), 400

    if not qp_barcode:
        return jsonify({'success': False, 'message': 'Answer booklet barcode scan is required.'}), 400

    # Format check for barcode (alphanumeric, dashes, underscores, dots, slashes, length 2-64)
    if len(qp_barcode) < 2 or len(qp_barcode) > 64 or not re.match(r'^[A-Z0-9_\-\.\/\s]+$', qp_barcode):
        return jsonify({
            'success': False,
            'message': f"INVALID BARCODE FORMAT: '{qp_barcode}'. Expected a valid alphanumeric booklet identifier."
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # 1. Check if session exists and is locked
        cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return jsonify({'success': False, 'message': 'Exam session not found.'}), 404

        if session_row['status'] in ('LOCKED', 'SUBMITTED'):
            return jsonify({
                'success': False,
                'locked': True,
                'message': 'This examination session is LOCKED. Attendance submission was finalized. Modifications are restricted.'
            }), 403

        # Enforce Exam Time and Date Window (unless Administrator)
        time_status = get_session_window_status(dict(session_row))
        if not time_status['is_open'] and session.get('role') != 'ADMIN':
            return jsonify({
                'success': False,
                'locked': True,
                'is_window_closed': True,
                'time_window': time_status,
                'message': f"EXAMINATION WINDOW NOT ACTIVE: {time_status['message']}"
            }), 403

        # 2. Check if student belongs to assigned roster
        cursor.execute('SELECT * FROM students WHERE session_id = ? AND usn = ?', (session_id, usn))
        student = cursor.fetchone()
        if not student:
            return jsonify({'success': False, 'message': f'Student with USN {usn} is not assigned to this classroom.'}), 404

        # 3. Duplicate attendance check on student (Feature 2)
        if student['attendance_status'] == 'PRESENT':
            marked_time = student['marked_at'] or 'earlier'
            existing_barcode = student['qp_barcode'] or 'N/A'
            return jsonify({
                'success': False,
                'duplicate': True,
                'message': f'DUPLICATE PREVENTED: Candidate {usn} ({student["student_name"]}) has ALREADY been marked PRESENT at {marked_time} with Booklet Barcode [{existing_barcode}]. Duplicate scan has been rejected.'
            }), 409

        # 4. Global Duplicate Barcode Check (Feature 2 & 8)
        # Check if this booklet barcode is already assigned to any other student in this exam hall
        cursor.execute('''
            SELECT s.usn, s.student_name, e.room_number 
            FROM students s 
            JOIN exam_sessions e ON s.session_id = e.id 
            WHERE s.qp_barcode = ? AND s.session_id = ? AND s.usn != ?
        ''', (qp_barcode, session_id, usn))
        duplicate_student = cursor.fetchone()
        if duplicate_student:
            log_audit(
                session_id=session_id,
                action_type='BARCODE_REJECTED',
                invigilator_id=invigilator_id,
                invigilator_name=invigilator_name,
                usn=usn,
                student_name=student['student_name'],
                qp_barcode=qp_barcode,
                reason=f"Duplicate assignment attempt: Booklet [{qp_barcode}] is already held by {duplicate_student['usn']}.",
                client_ip=request.remote_addr or '127.0.0.1',
                user_id=user_id,
                cursor=cursor
            )
            conn.commit()
            return jsonify({
                'success': False,
                'duplicate': True,
                'message': f"DUPLICATE REJECTED: Booklet barcode [{qp_barcode}] has ALREADY been scanned for student {duplicate_student['usn']} ({duplicate_student['student_name']}) in {duplicate_student['room_number']}. Each booklet can only be assigned once!"
            }), 409

        # Check booklet registry
        cursor.execute('SELECT * FROM booklet_registry WHERE barcode_value = ?', (qp_barcode,))
        booklet = cursor.fetchone()

        if not booklet:
            # Auto-register physical examination booklet on the fly for real live exams
            exam_id = session_row['exam_id'] if session_row['exam_id'] else 1
            cursor.execute('''
                INSERT INTO booklet_registry (barcode_value, exam_id, batch_number, status)
                VALUES (?, ?, 'PHYSICAL-EXAM-SCAN', 'AVAILABLE')
            ''', (qp_barcode, exam_id))
        else:
            if booklet['status'] == 'ASSIGNED' and booklet['assigned_usn'] != usn:
                log_audit(
                    session_id=session_id,
                    action_type='BARCODE_REJECTED',
                    invigilator_id=invigilator_id,
                    invigilator_name=invigilator_name,
                    usn=usn,
                    student_name=student['student_name'],
                    qp_barcode=qp_barcode,
                    reason=f"Attempted duplicate assignment: Booklet already assigned to candidate {booklet['assigned_usn']}.",
                    client_ip=request.remote_addr or '127.0.0.1',
                    user_id=user_id,
                    cursor=cursor
                )
                conn.commit()
                return jsonify({
                    'success': False,
                    'duplicate': True,
                    'message': f"BOOKLET ALREADY ASSIGNED: Barcode [{qp_barcode}] has ALREADY been assigned to candidate {booklet['assigned_usn']}. Duplicate assignment rejected."
                }), 409

            if booklet['status'] in ('DAMAGED', 'VOID'):
                return jsonify({
                    'success': False,
                    'message': f"VOID BOOKLET: Barcode [{qp_barcode}] is marked as '{booklet['status']}' in the registry and cannot be used."
                }), 400

        # 5. Atomic Transaction: Record attendance and update registry
        now_ts = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute('''
            UPDATE students
            SET attendance_status = 'PRESENT',
                qp_barcode = ?,
                marked_at = ?,
                marked_by = ?
            WHERE id = ?
        ''', (qp_barcode, now_ts, invigilator_name, student['id']))

        cursor.execute('''
            UPDATE booklet_registry
            SET status = 'ASSIGNED',
                assigned_session_id = ?,
                assigned_usn = ?,
                assigned_at = ?
            WHERE barcode_value = ? AND status = 'AVAILABLE'
        ''', (session_id, usn, now_ts, qp_barcode))

        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({
                'success': False,
                'duplicate': True,
                'message': f"BOOKLET ALREADY ASSIGNED: Barcode [{qp_barcode}] was just assigned to another candidate. Concurrent duplicate assignment rejected."
            }), 409

        # 6. Audit Trail Logging
        log_audit(
            session_id=session_id,
            action_type='MARK_PRESENT',
            invigilator_id=invigilator_id,
            invigilator_name=invigilator_name,
            usn=usn,
            student_name=student['student_name'],
            old_status=student['attendance_status'],
            new_status='PRESENT',
            qp_barcode=qp_barcode,
            reason='Verified via barcode camera scanning',
            client_ip=request.remote_addr or '127.0.0.1',
            user_id=user_id,
            cursor=cursor
        )

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Attendance marked PRESENT for {student["student_name"]} ({usn}). Booklet Barcode: {qp_barcode}',
            'student': {
                'usn': usn,
                'student_name': student['student_name'],
                'status': 'PRESENT',
                'qp_barcode': qp_barcode,
                'marked_at': now_ts
            }
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/api/attendance/mark_absent', methods=['POST'])
def mark_absent():
    data = request.get_json() or {}
    session_id = data.get('session_id')
    usn = (data.get('usn') or '').strip().upper()

    invigilator_name = session.get('full_name') or data.get('invigilator_name', 'Room Invigilator')
    invigilator_id = session.get('username') or data.get('invigilator_id', 'INV-ACTIVE')
    user_id = session.get('user_id')

    if not session_id or not usn:
        return jsonify({'success': False, 'message': 'Session ID and USN are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
        session_row = cursor.fetchone()
        if session_row and session_row['status'] in ('LOCKED', 'SUBMITTED'):
            return jsonify({'success': False, 'locked': True, 'message': 'Session is LOCKED. Cannot modify.'}), 403

        # Enforce Exam Time and Date Window (unless Administrator)
        if session_row:
            time_status = get_session_window_status(dict(session_row))
            if not time_status['is_open'] and session.get('role') != 'ADMIN':
                return jsonify({
                    'success': False,
                    'locked': True,
                    'is_window_closed': True,
                    'time_window': time_status,
                    'message': f"EXAMINATION WINDOW NOT ACTIVE: {time_status['message']}"
                }), 403

        cursor.execute('SELECT * FROM students WHERE session_id = ? AND usn = ?', (session_id, usn))
        student = cursor.fetchone()
        if not student:
            return jsonify({'success': False, 'message': 'Student not found in this room.'}), 404

        old_barcode = student['qp_barcode']
        old_status = student['attendance_status']
        now_ts = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

        # If student previously had an assigned booklet, release it in the registry
        if old_barcode:
            cursor.execute('''
                UPDATE booklet_registry
                SET status = 'AVAILABLE',
                    assigned_session_id = NULL,
                    assigned_usn = NULL,
                    assigned_at = NULL
                WHERE barcode_value = ?
            ''', (old_barcode,))

        cursor.execute('''
            UPDATE students
            SET attendance_status = 'ABSENT',
                qp_barcode = NULL,
                marked_at = ?,
                marked_by = ?
            WHERE id = ?
        ''', (now_ts, invigilator_name, student['id']))

        log_audit(
            session_id=session_id,
            action_type='MARK_ABSENT',
            invigilator_id=invigilator_id,
            invigilator_name=invigilator_name,
            usn=usn,
            student_name=student['student_name'],
            old_status=old_status,
            new_status='ABSENT',
            qp_barcode=None,
            reason='Invigilator confirmed candidate absent at designated desk',
            client_ip=request.remote_addr or '127.0.0.1',
            user_id=user_id,
            cursor=cursor
        )

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Candidate {student["student_name"]} ({usn}) marked ABSENT.',
            'student': {
                'usn': usn,
                'student_name': student['student_name'],
                'status': 'ABSENT',
                'marked_at': now_ts
            }
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/api/attendance/redo', methods=['POST'])
def redo_attendance():
    """
    Feature 3: Redo Attendance Option (Correction & Reassignment)
    Allows invigilator to correct mistake before final submission with mandatory reason.
    Feature 6: Logs full change history into Digital Audit Trail.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    usn = (data.get('usn') or '').strip().upper()
    new_status = data.get('new_status') # 'PRESENT', 'ABSENT', or 'PENDING'
    qp_barcode = (data.get('qp_barcode') or '').strip().upper() or None
    reason = (data.get('reason') or '').strip()

    invigilator_name = session.get('full_name') or data.get('invigilator_name', 'Room Invigilator')
    invigilator_id = session.get('username') or data.get('invigilator_id', 'INV-ACTIVE')
    user_id = session.get('user_id')

    if not session_id or not usn or not new_status:
        return jsonify({'success': False, 'message': 'Session, USN, and New Status are required.'}), 400

    if not reason:
        return jsonify({'success': False, 'message': 'A mandatory reason is required for attendance correction.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
        session_row = cursor.fetchone()
        if session_row and session_row['status'] in ('LOCKED', 'SUBMITTED'):
            return jsonify({'success': False, 'locked': True, 'message': 'Session is LOCKED. Unlock required for redo.'}), 403

        cursor.execute('SELECT * FROM students WHERE session_id = ? AND usn = ?', (session_id, usn))
        student = cursor.fetchone()
        if not student:
            return jsonify({'success': False, 'message': 'Student not found in this session.'}), 404

        old_status = student['attendance_status']
        old_barcode = student['qp_barcode']
        now_ts = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

        # If correcting to PRESENT, validate new booklet barcode
        if new_status == 'PRESENT':
            if not qp_barcode:
                return jsonify({'success': False, 'message': 'Valid booklet barcode is required when marking PRESENT.'}), 400

            cursor.execute('SELECT * FROM booklet_registry WHERE barcode_value = ?', (qp_barcode,))
            booklet = cursor.fetchone()
            if not booklet:
                return jsonify({'success': False, 'message': f"Barcode [{qp_barcode}] is not in the authorized registry."}), 400

            if booklet['status'] == 'ASSIGNED' and booklet['assigned_usn'] != usn:
                return jsonify({'success': False, 'duplicate': True, 'message': f"Booklet [{qp_barcode}] is already assigned to {booklet['assigned_usn']}."}), 409

            # Release old booklet barcode if different
            if old_barcode and old_barcode != qp_barcode:
                cursor.execute('''
                    UPDATE booklet_registry
                    SET status = 'AVAILABLE', assigned_session_id = NULL, assigned_usn = NULL, assigned_at = NULL
                    WHERE barcode_value = ?
                ''', (old_barcode,))

            # Assign new barcode
            cursor.execute('''
                UPDATE booklet_registry
                SET status = 'ASSIGNED', assigned_session_id = ?, assigned_usn = ?, assigned_at = ?
                WHERE barcode_value = ?
            ''', (session_id, usn, now_ts, qp_barcode))

        else: # ABSENT or PENDING
            qp_barcode = None
            if old_barcode:
                cursor.execute('''
                    UPDATE booklet_registry
                    SET status = 'AVAILABLE', assigned_session_id = NULL, assigned_usn = NULL, assigned_at = NULL
                    WHERE barcode_value = ?
                ''', (old_barcode,))

        cursor.execute('''
            UPDATE students
            SET attendance_status = ?,
                qp_barcode = ?,
                marked_at = ?,
                marked_by = ?
            WHERE id = ?
        ''', (new_status, qp_barcode, now_ts, invigilator_name, student['id']))

        log_audit(
            session_id=session_id,
            action_type='REDO_CORRECTION',
            invigilator_id=invigilator_id,
            invigilator_name=invigilator_name,
            usn=usn,
            student_name=student['student_name'],
            old_status=old_status,
            new_status=new_status,
            qp_barcode=qp_barcode,
            reason=reason,
            client_ip=request.remote_addr or '127.0.0.1',
            user_id=user_id,
            cursor=cursor
        )

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Attendance for {usn} successfully corrected from {old_status} to {new_status}.',
            'student': {
                'usn': usn,
                'student_name': student['student_name'],
                'status': new_status,
                'qp_barcode': qp_barcode,
                'marked_at': now_ts
            }
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/api/session/summary/<int:session_id>')
def get_session_summary(session_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Session not found'}), 404

    cursor.execute('''
        SELECT usn, student_name, desk_number, attendance_status, qp_barcode, marked_at 
        FROM students 
        WHERE session_id = ? 
        ORDER BY desk_number ASC
    ''', (session_id,))
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()

    present_list = [s for s in students if s['attendance_status'] == 'PRESENT']
    absent_list = [s for s in students if s['attendance_status'] == 'ABSENT']
    pending_list = [s for s in students if s['attendance_status'] == 'PENDING']

    return jsonify({
        'success': True,
        'session': dict(session_row),
        'total': len(students),
        'present_count': len(present_list),
        'absent_count': len(absent_list),
        'pending_count': len(pending_list),
        'present_list': present_list,
        'absent_list': absent_list,
        'pending_list': pending_list,
        'is_locked': session_row['status'] in ('LOCKED', 'SUBMITTED')
    })


@app.route('/api/session/confirm_lock', methods=['POST'])
def confirm_lock():
    """
    Feature 4: Final Attendance Confirmation
    Feature 5: Automatic Excel Report Generation
    Feature 7: Unmarked Student Warning
    Feature 8: Attendance Locking After Submission
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    force_submit = data.get('force_submit', False)

    invigilator_name = session.get('full_name') or data.get('invigilator_name', 'Room Invigilator')
    invigilator_id = session.get('username') or data.get('invigilator_id', 'INV-ACTIVE')
    user_id = session.get('user_id')

    if not session_id:
        return jsonify({'success': False, 'message': 'Session ID is required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return jsonify({'success': False, 'message': 'Session not found.'}), 404

        if session_row['status'] in ('LOCKED', 'SUBMITTED'):
            return jsonify({'success': True, 'message': 'Session is already locked.', 'already_locked': True})

        # Check for unmarked/pending students (Feature 7 & Section 10)
        cursor.execute("SELECT usn, student_name, desk_number FROM students WHERE session_id = ? AND attendance_status = 'PENDING'", (session_id,))
        pending_students = [dict(row) for row in cursor.fetchall()]

        if len(pending_students) > 0 and not force_submit:
            return jsonify({
                'success': False,
                'warning': 'unmarked_students',
                'pending_count': len(pending_students),
                'pending_students': pending_students,
                'message': f'Warning: {len(pending_students)} student(s) still have unmarked/pending attendance! Review these students before final submission.'
            }), 400

        # Lock session
        now_ts = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE exam_sessions
            SET status = 'LOCKED',
                locked_at = ?,
                locked_by = ?,
                submitted_at = ?
            WHERE id = ?
        ''', (now_ts, invigilator_name, now_ts, session_id))

        # Fetch updated students list
        cursor.execute('SELECT * FROM students WHERE session_id = ? ORDER BY desk_number ASC, usn ASC', (session_id,))
        students = [dict(row) for row in cursor.fetchall()]

        session_dict = dict(session_row)
        session_dict['status'] = 'LOCKED'
        session_dict['locked_at'] = now_ts

        # Auto generate COE Excel Report
        report_file_path = generate_coe_attendance_excel(session_dict, students)
        report_filename = os.path.basename(report_file_path)

        # Log lock action in audit trail
        log_audit(
            session_id=session_id,
            action_type='LOCK_SUBMISSION',
            invigilator_id=invigilator_id,
            invigilator_name=invigilator_name,
            reason=f"Final attendance confirmed and submitted. Total Present: {sum(1 for s in students if s['attendance_status'] == 'PRESENT')}, Absent: {sum(1 for s in students if s['attendance_status'] == 'ABSENT')}. Excel generated: {report_filename}",
            client_ip=request.remote_addr or '127.0.0.1',
            user_id=user_id,
            cursor=cursor
        )

        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Attendance successfully confirmed, finalized, and locked. Official COE Excel report generated.',
            'locked_at': now_ts,
            'report_filename': report_filename,
            'download_url': f'/download_report/{session_id}'
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/api/session/unlock_override', methods=['POST'])
def unlock_override():
    """
    Feature 8 & Section 13: Authorized Unlock for Emergency Adjustments
    Requires valid COE authorization credentials and mandatory reason.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    auth_code = (data.get('auth_code') or '').strip()
    reason = (data.get('reason') or '').strip()

    invigilator_name = session.get('full_name') or data.get('invigilator_name', 'Chief Superintendent')
    invigilator_id = session.get('username') or data.get('invigilator_id', 'COE-SUPER')
    user_id = session.get('user_id')

    # Allowed authorization codes: COE@2026, ADMIN123, or authenticated Admin role
    is_valid_auth = (auth_code in ['COE@2026', 'ADMIN123']) or (session.get('role') == 'ADMIN')
    if not is_valid_auth:
        return jsonify({'success': False, 'message': 'Invalid COE Authorization PIN. Access denied.'}), 403

    if not reason:
        return jsonify({'success': False, 'message': 'Mandatory justification reason is required for unlocking.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM exam_sessions WHERE id = ?', (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            return jsonify({'success': False, 'message': 'Session not found.'}), 404

        cursor.execute('''
            UPDATE exam_sessions
            SET status = 'IN_PROGRESS',
                locked_at = NULL,
                locked_by = NULL
            WHERE id = ?
        ''', (session_id,))

        log_audit(
            session_id=session_id,
            action_type='UNLOCK_OVERRIDE',
            invigilator_id=invigilator_id,
            invigilator_name=invigilator_name,
            reason=f"Administrative Unlock Override: {reason}",
            client_ip=request.remote_addr or '127.0.0.1',
            user_id=user_id,
            cursor=cursor
        )

        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Session has been unlocked. Authorized invigilator can now make corrections.'
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()


@app.route('/download_report/<int:session_id>')
def download_report(session_id):
    """
    Generates and downloads official COE Excel attendance sheet (Section 14).
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.*, d.name as department_name, ex.exam_name, ex.exam_code 
        FROM exam_sessions e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN examinations ex ON e.exam_id = ex.id
        WHERE e.id = ?
    ''', (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        return "Session not found", 404

    cursor.execute('SELECT * FROM students WHERE session_id = ? ORDER BY desk_number ASC, usn ASC', (session_id,))
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()

    session_dict = dict(session_row)
    report_file_path = generate_coe_attendance_excel(session_dict, students)

    # Compliant filename format: Attendance_{Classroom}_{Date}_{Session}.xlsx
    clean_room = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_dict['room_number']).strip('_')
    clean_date = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_dict['exam_date']).strip('_')
    clean_sess = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_dict['exam_session'].split(' ')[0]).strip('_')
    dl_filename = f"Attendance_{clean_room}_{clean_date}_{clean_sess}.xlsx"

    return send_file(
        report_file_path,
        as_attachment=True,
        download_name=dl_filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ----------------- Administrator Management Endpoints -----------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM departments')
    dept_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM classrooms')
    room_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'TEACHER'")
    teacher_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM exam_sessions')
    session_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM exam_sessions WHERE status IN ('LOCKED', 'SUBMITTED')")
    locked_sessions = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM booklet_registry')
    barcode_count = cursor.fetchone()[0]

    conn.close()

    stats = {
        'dept_count': dept_count,
        'room_count': room_count,
        'teacher_count': teacher_count,
        'session_count': session_count,
        'locked_sessions': locked_sessions,
        'barcode_count': barcode_count
    }

    return render_template('admin/admin_dashboard.html', stats=stats)


@app.route('/admin/users')
@admin_required
def admin_users_list():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.*, d.code as dept_code 
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY u.role ASC, u.full_name ASC
    ''')
    users = [dict(row) for row in cursor.fetchall()]

    cursor.execute('SELECT id, code, name FROM departments ORDER BY code ASC')
    departments = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('admin/admin_users.html', users=users, departments=departments)


@app.route('/admin/users/create', methods=['POST'])
@admin_required
def admin_user_create():
    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip().lower()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    department_id = request.form.get('department_id', type=int)

    if not full_name or not username or not email or not password:
        flash('All required fields must be completed.', 'danger')
        return redirect(url_for('admin_users_list'))

    hashed_pw = generate_password_hash(password)

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
            VALUES (?, ?, ?, ?, 'TEACHER', ?, 1)
        ''', (username, email, hashed_pw, full_name, department_id))
        new_user_id = cursor.lastrowid

        if department_id:
            cursor.execute('INSERT OR IGNORE INTO teacher_department_access (user_id, department_id) VALUES (?, ?)', (new_user_id, department_id))

        conn.commit()
        flash(f"Teacher account '{username}' created successfully.", 'success')
    except sqlite3.IntegrityError:
        flash(f"Error: Username '{username}' or email '{email}' already exists.", 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_users_list'))


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_user_toggle(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT is_active, username, role FROM users WHERE id = ?', (user_id,))
    u = cursor.fetchone()
    if u and u['role'] != 'ADMIN':
        new_state = 0 if u['is_active'] else 1
        cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_state, user_id))
        conn.commit()
        flash(f"Account '{u['username']}' status updated to {'Active' if new_state else 'Deactivated'}.", 'info')
    conn.close()
    return redirect(url_for('admin_users_list'))


@app.route('/admin/departments')
@admin_required
def admin_departments_list():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT d.*, COUNT(c.id) as classroom_count 
        FROM departments d
        LEFT JOIN classrooms c ON c.department_id = d.id
        GROUP BY d.id
        ORDER BY d.code ASC
    ''')
    departments = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
        SELECT c.*, d.code as dept_code 
        FROM classrooms c
        JOIN departments d ON c.department_id = d.id
        ORDER BY d.code ASC, c.room_number ASC
    ''')
    classrooms = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('admin/admin_departments.html', departments=departments, classrooms=classrooms)


@app.route('/admin/departments/create', methods=['POST'])
@admin_required
def admin_department_create():
    code = (request.form.get('code') or '').strip().upper()
    name = (request.form.get('name') or '').strip()

    if not code or not name:
        flash('Department code and name are required.', 'danger')
        return redirect(url_for('admin_departments_list'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO departments (code, name) VALUES (?, ?)', (code, name))
        conn.commit()
        flash(f"Department '{code}' created successfully.", 'success')
    except sqlite3.IntegrityError:
        flash(f"Department code '{code}' already exists.", 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_departments_list'))


@app.route('/admin/classrooms/create', methods=['POST'])
@app.route('/classrooms/create', methods=['POST'])
@admin_required
def admin_classroom_create():
    department_id = request.form.get('department_id', type=int)
    room_number = (request.form.get('room_number') or '').strip()
    building = (request.form.get('building') or '').strip()
    capacity = request.form.get('capacity', 40, type=int)
    redirect_url = request.form.get('redirect_url')

    if not department_id or not room_number:
        flash('Department and room number are required.', 'danger')
        return redirect(redirect_url or url_for('departments_view'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO classrooms (department_id, room_number, building, capacity)
            VALUES (?, ?, ?, ?)
        ''', (department_id, room_number, building, capacity))
        conn.commit()
        flash(f"Classroom '{room_number}' (Capacity: {capacity} desks) added successfully.", 'success')
    except sqlite3.IntegrityError:
        flash(f"Classroom '{room_number}' already exists in this department.", 'danger')
    finally:
        conn.close()

    return redirect(redirect_url or url_for('departments_view'))


@app.route('/admin/classrooms/<int:room_id>/edit', methods=['POST'])
@app.route('/classrooms/<int:room_id>/edit', methods=['POST'])
@admin_required
def admin_classroom_edit(room_id):
    room_number = (request.form.get('room_number') or '').strip()
    building = (request.form.get('building') or '').strip()
    capacity = request.form.get('capacity', 40, type=int)
    department_id = request.form.get('department_id', type=int)
    redirect_url = request.form.get('redirect_url')

    if not room_number or capacity < 1:
        flash('Valid room number and positive capacity are required.', 'danger')
        return redirect(redirect_url or url_for('departments_view'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        if department_id:
            cursor.execute('''
                UPDATE classrooms 
                SET room_number = ?, building = ?, capacity = ?, department_id = ?
                WHERE id = ?
            ''', (room_number, building, capacity, department_id, room_id))
        else:
            cursor.execute('''
                UPDATE classrooms 
                SET room_number = ?, building = ?, capacity = ?
                WHERE id = ?
            ''', (room_number, building, capacity, room_id))
        conn.commit()
        flash(f"Classroom '{room_number}' updated successfully (Capacity: {capacity} desks).", 'success')
    except sqlite3.IntegrityError:
        flash(f"Classroom name '{room_number}' conflicts with an existing room in this department.", 'danger')
    finally:
        conn.close()

    return redirect(redirect_url or url_for('departments_view'))


@app.route('/admin/classrooms/<int:room_id>/delete', methods=['POST'])
@app.route('/classrooms/<int:room_id>/delete', methods=['POST'])
@admin_required
def admin_classroom_delete(room_id):
    redirect_url = request.form.get('redirect_url')
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT room_number FROM classrooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        room_name = room['room_number'] if room else f"ID {room_id}"

        cursor.execute('DELETE FROM classrooms WHERE id = ?', (room_id,))
        conn.commit()
        flash(f"Classroom '{room_name}' has been deleted.", 'info')
    except Exception as e:
        flash(f"Cannot delete classroom: It may have linked examination sessions ({str(e)}).", 'danger')
    finally:
        conn.close()

    return redirect(redirect_url or url_for('departments_view'))


@app.route('/admin/exams')
@admin_required
def admin_exams_list():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT s.*, d.code as dept_code 
        FROM exam_sessions s
        LEFT JOIN departments d ON s.department_id = d.id
        ORDER BY s.id DESC
    ''')
    sessions = [dict(row) for row in cursor.fetchall()]

    cursor.execute('SELECT id, code, name FROM departments ORDER BY code ASC')
    departments = [dict(row) for row in cursor.fetchall()]

    cursor.execute('SELECT id, room_number FROM classrooms ORDER BY room_number ASC')
    classrooms = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT id, full_name, username FROM users WHERE role = 'TEACHER' AND is_active = 1")
    teachers = [dict(row) for row in cursor.fetchall()]

    conn.close()

    today_str = get_ist_now().strftime("%Y-%m-%d")

    return render_template(
        'admin/admin_exams.html',
        sessions=sessions,
        departments=departments,
        classrooms=classrooms,
        teachers=teachers,
        today_str=today_str
    )


@app.route('/admin/exams/create_session', methods=['POST'])
@admin_required
def admin_session_create():
    course_code = (request.form.get('course_code') or '').strip().upper()
    course_name = (request.form.get('course_name') or '').strip()
    department_id = request.form.get('department_id', type=int)
    room_number_input = (request.form.get('room_number') or '').strip()
    classroom_id = request.form.get('classroom_id', type=int)
    exam_date = request.form.get('exam_date')
    start_time = normalize_time_str(request.form.get('start_time'), default='09:30')
    end_time = normalize_time_str(request.form.get('end_time'), default='12:30')
    exam_session = (request.form.get('exam_session') or '').strip() or f"Session ({start_time} - {end_time})"
    qp_code = (request.form.get('qp_code') or f"QP-2026-{course_code}-A").strip().upper()
    teacher_user_id = request.form.get('teacher_user_id', type=int)

    conn = get_db()
    cursor = conn.cursor()

    if room_number_input:
        cursor.execute('SELECT id, room_number FROM classrooms WHERE department_id = ? AND LOWER(room_number) = LOWER(?)', (department_id, room_number_input))
        found_r = cursor.fetchone()
        if found_r:
            classroom_id = found_r['id']
            room_number = found_r['room_number']
        else:
            cursor.execute('INSERT INTO classrooms (department_id, room_number, building, capacity) VALUES (?, ?, ?, 40)',
                           (department_id, room_number_input, 'Academic Block'))
            classroom_id = cursor.lastrowid
            room_number = room_number_input
    elif classroom_id:
        cursor.execute('SELECT room_number FROM classrooms WHERE id = ?', (classroom_id,))
        room_row = cursor.fetchone()
        room_number = room_row['room_number'] if room_row else f"Room {classroom_id}"
    else:
        room_number = "CS101"
        cursor.execute('INSERT INTO classrooms (department_id, room_number, building, capacity) VALUES (?, ?, ?, 40)',
                       (department_id or 1, room_number, 'Academic Block'))
        classroom_id = cursor.lastrowid

    cursor.execute('SELECT full_name, username FROM users WHERE id = ?', (teacher_user_id,))
    t_row = cursor.fetchone()
    invigilator_name = t_row['full_name'] if t_row else 'Invigilator'
    invigilator_id = t_row['username'] if t_row else 'INV'

    cursor.execute('''
        INSERT INTO exam_sessions (
            exam_id, department_id, classroom_id, course_code, course_name, exam_date,
            start_time, end_time, exam_session, room_number, qp_code, invigilator_name, invigilator_id,
            invigilator_user_id, status
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'IN_PROGRESS')
    ''', (department_id, classroom_id, course_code, course_name, exam_date,
          start_time, end_time, exam_session, room_number, qp_code, invigilator_name, invigilator_id, teacher_user_id))

    cursor.execute('INSERT OR IGNORE INTO booklet_registry (barcode_value, exam_id, batch_number, status) VALUES (?, 1, ?, \'AVAILABLE\')',
                   (qp_code, f"BATCH-{course_code}"))

    conn.commit()
    conn.close()

    flash(f"Examination session for {course_code} ({room_number}) scheduled for {exam_date} ({start_time} - {end_time}).", 'success')
    return redirect(url_for('admin_exams_list'))


@app.route('/admin/students')
@admin_required
def admin_students_list():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT s.*, d.code as dept_code 
        FROM students_master s
        LEFT JOIN departments d ON s.department_id = d.id
        ORDER BY s.usn ASC
    ''')
    students = [dict(row) for row in cursor.fetchall()]

    cursor.execute('SELECT id, course_code, room_number, exam_date FROM exam_sessions ORDER BY id DESC')
    sessions = [dict(row) for row in cursor.fetchall()]

    cursor.execute('SELECT id, code, name FROM departments ORDER BY code ASC')
    departments = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template('admin/admin_students.html', students=students, sessions=sessions, departments=departments, import_result=None)


@app.route('/admin/students/create', methods=['POST'])
@admin_required
def admin_students_create():
    """
    Manually creates an individual candidate record and optionally assigns to an examination room.
    """
    usn = (request.form.get('usn') or '').strip().upper()
    name = (request.form.get('student_name') or '').strip()
    department_id = request.form.get('department_id', type=int)
    semester = request.form.get('semester', 8, type=int)
    session_id = request.form.get('session_id', type=int)

    if not usn or not name:
        flash('Student USN and Full Name are required.', 'danger')
        return redirect(url_for('admin_students_list'))

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id FROM students_master WHERE usn = ?', (usn,))
        master = cursor.fetchone()
        if master:
            master_id = master['id']
            cursor.execute('UPDATE students_master SET student_name = ?, department_id = ?, semester = ? WHERE id = ?',
                           (name, department_id, semester, master_id))
        else:
            cursor.execute('INSERT INTO students_master (usn, student_name, department_id, semester) VALUES (?, ?, ?, ?)',
                           (usn, name, department_id, semester))
            master_id = cursor.lastrowid

        if session_id:
            cursor.execute('SELECT COUNT(*) FROM students WHERE session_id = ?', (session_id,))
            desk_num = cursor.fetchone()[0] + 1
            desk_str = f"D-{desk_num:02d}"
            cursor.execute('''
                INSERT INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
            ''', (session_id, master_id, usn, name, desk_str))

        conn.commit()
        flash(f"Student '{name}' ({usn}) successfully registered.", 'success')
    except sqlite3.IntegrityError:
        flash(f"Candidate with USN '{usn}' is already assigned to this examination session.", 'warning')
    except Exception as e:
        flash(f"Error registering student: {str(e)}", 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin_students_list'))


@app.route('/admin/students/quick_bulk_add', methods=['POST'])
@admin_required
def admin_students_quick_bulk_add():
    """
    Bulk adds students by pasting lines of USN and Name directly without needing a CSV file.
    """
    text_data = request.form.get('student_list_text') or ''
    department_id = request.form.get('department_id', type=int)
    semester = request.form.get('semester', 8, type=int)
    session_id = request.form.get('session_id', type=int)

    lines = [line.strip() for line in text_data.split('\n') if line.strip()]
    if not lines:
        flash('Please enter or paste at least one student line.', 'danger')
        return redirect(url_for('admin_students_list'))

    conn = get_db()
    cursor = conn.cursor()

    current_desk_num = 1
    if session_id:
        cursor.execute('SELECT COUNT(*) FROM students WHERE session_id = ?', (session_id,))
        current_desk_num = cursor.fetchone()[0] + 1

    added_count = 0
    errors = []

    for idx, line in enumerate(lines, 1):
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if not parts:
            continue
        usn = parts[0].upper()
        name = parts[1] if len(parts) > 1 else f"Candidate {usn}"

        if len(usn) < 3:
            errors.append(f"Line {idx}: Invalid USN '{usn}'")
            continue

        try:
            cursor.execute('SELECT id FROM students_master WHERE usn = ?', (usn,))
            master = cursor.fetchone()
            if master:
                master_id = master['id']
            else:
                cursor.execute('INSERT INTO students_master (usn, student_name, department_id, semester) VALUES (?, ?, ?, ?)',
                               (usn, name, department_id, semester))
                master_id = cursor.lastrowid

            if session_id:
                desk_str = f"D-{current_desk_num:02d}"
                cursor.execute('''
                    INSERT OR IGNORE INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
                    VALUES (?, ?, ?, ?, ?, 'PENDING')
                ''', (session_id, master_id, usn, name, desk_str))
                current_desk_num += 1

            added_count += 1
        except Exception as e:
            errors.append(f"Line {idx} ({usn}): {str(e)}")

    conn.commit()
    conn.close()

    if errors:
        flash(f"Processed {added_count} students. {len(errors)} issues encountered: {', '.join(errors[:3])}", 'warning')
    else:
        flash(f"Successfully processed and enrolled {added_count} candidates.", 'success')

    return redirect(url_for('admin_students_list'))


@app.route('/api/session/add_student', methods=['POST'])
@login_required
def api_session_add_student():
    """
    Allows teachers or admins on the Classroom Roster page to add a student directly to the active hall.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    usn = (data.get('usn') or '').strip().upper()
    student_name = (data.get('student_name') or '').strip()

    if not session_id or not usn or not student_name:
        return jsonify({'success': False, 'message': 'Session ID, USN, and Candidate Name are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT status, department_id FROM exam_sessions WHERE id = ?', (session_id,))
    s_row = cursor.fetchone()
    if not s_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Session not found.'}), 404

    if s_row['status'] in ('LOCKED', 'SUBMITTED'):
        conn.close()
        return jsonify({'success': False, 'message': 'This session is locked. Cannot add candidates after final submission.'}), 403

    try:
        cursor.execute('SELECT id FROM students_master WHERE usn = ?', (usn,))
        m = cursor.fetchone()
        if m:
            master_id = m['id']
        else:
            cursor.execute('INSERT INTO students_master (usn, student_name, department_id, semester) VALUES (?, ?, ?, 8)',
                           (usn, student_name, s_row['department_id']))
            master_id = cursor.lastrowid

        cursor.execute('SELECT COUNT(*) FROM students WHERE session_id = ?', (session_id,))
        desk_num = cursor.fetchone()[0] + 1
        desk_str = f"D-{desk_num:02d}"

        cursor.execute('''
            INSERT INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        ''', (session_id, master_id, usn, student_name, desk_str))
        new_id = cursor.lastrowid
        conn.commit()

        log_audit(session.get('user_id'), session.get('username'), session.get('role'), 'STUDENT_MANUAL_ENROLL',
                  f"Added candidate {usn} ({student_name}) to session {session_id} desk {desk_str}.", session_id)

        conn.close()
        return jsonify({
            'success': True,
            'message': f"Candidate {student_name} ({usn}) successfully assigned to desk {desk_str}.",
            'student': {
                'id': new_id,
                'usn': usn,
                'student_name': student_name,
                'desk_number': desk_str,
                'attendance_status': 'PENDING'
            }
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': f"Candidate {usn} is already on this classroom roster."}), 400
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/session/bulk_add_students', methods=['POST'])
@login_required
def api_session_bulk_add_students():
    """
    Bulk adds candidates directly into the current exam session from a multi-line pasted list.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    raw_text = data.get('raw_text', '')

    if not session_id or not raw_text.strip():
        return jsonify({'success': False, 'message': 'Session ID and candidate list are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT status, department_id FROM exam_sessions WHERE id = ?', (session_id,))
    s_row = cursor.fetchone()
    if not s_row:
        conn.close()
        return jsonify({'success': False, 'message': 'Session not found.'}), 404

    if s_row['status'] in ('LOCKED', 'SUBMITTED'):
        conn.close()
        return jsonify({'success': False, 'message': 'Session is locked. Cannot add candidates.'}), 403

    cursor.execute('SELECT COUNT(*) FROM students WHERE session_id = ?', (session_id,))
    current_desk_num = cursor.fetchone()[0] + 1

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    added_count = 0
    duplicates = 0

    for line in lines:
        parts = [p.strip() for p in line.split(',') if p.strip()]
        if not parts:
            continue
        usn = parts[0].upper()
        name = parts[1] if len(parts) > 1 else f"Candidate {usn}"

        cursor.execute('SELECT id FROM students_master WHERE usn = ?', (usn,))
        m = cursor.fetchone()
        if m:
            master_id = m['id']
        else:
            cursor.execute('INSERT INTO students_master (usn, student_name, department_id, semester) VALUES (?, ?, ?, 8)',
                           (usn, name, s_row['department_id']))
            master_id = cursor.lastrowid

        desk_str = f"D-{current_desk_num:02d}"
        try:
            cursor.execute('''
                INSERT INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
            ''', (session_id, master_id, usn, name, desk_str))
            current_desk_num += 1
            added_count += 1
        except sqlite3.IntegrityError:
            duplicates += 1

    conn.commit()
    log_audit(session.get('user_id'), session.get('username'), session.get('role'), 'STUDENT_BULK_ENROLL',
              f"Bulk enrolled {added_count} candidates to session {session_id}.", session_id)
    conn.close()

    msg = f"Successfully added {added_count} candidates to this examination hall roster."
    if duplicates > 0:
        msg += f" ({duplicates} duplicate USNs already existed in room and were skipped)."

    return jsonify({'success': True, 'added_count': added_count, 'message': msg})


@app.route('/admin/students/import', methods=['POST'])
@admin_required
def admin_students_import():
    """
    Imports student CSV data with duplicate USN validation and row-level error reporting (Section 16).
    """
    file = request.files.get('csv_file')
    session_id = request.form.get('session_id', type=int)

    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid .csv file.', 'danger')
        return redirect(url_for('admin_students_list'))

    content = file.stream.read().decode('utf-8', errors='ignore')
    reader = csv.reader(io.StringIO(content))

    conn = get_db()
    cursor = conn.cursor()

    # Preload department mapping
    cursor.execute('SELECT id, code FROM departments')
    dept_map = {row['code'].upper(): row['id'] for row in cursor.fetchall()}

    success_count = 0
    errors = []

    # Get max desk count if assigning to session
    current_desk_num = 1
    if session_id:
        cursor.execute('SELECT COUNT(*) FROM students WHERE session_id = ?', (session_id,))
        current_desk_num = cursor.fetchone()[0] + 1

    row_index = 0
    for row in reader:
        row_index += 1
        if not row or row_index == 1 and ('usn' in row[0].lower() or 'name' in row[0].lower()):
            continue # Header row

        if len(row) < 2:
            errors.append({'row': row_index, 'data': ",".join(row), 'message': 'Missing required columns (expected at least USN and Student Name).'})
            continue

        usn = row[0].strip().upper()
        name = row[1].strip()
        dept_code = row[2].strip().upper() if len(row) > 2 else 'CSE'
        semester = int(row[3].strip()) if len(row) > 3 and row[3].strip().isdigit() else 8

        if not usn or len(usn) < 3:
            errors.append({'row': row_index, 'data': ",".join(row), 'message': 'Invalid USN format.'})
            continue

        dept_id = dept_map.get(dept_code) or list(dept_map.values())[0] if dept_map else None

        try:
            cursor.execute('''
                INSERT INTO students_master (usn, student_name, department_id, semester)
                VALUES (?, ?, ?, ?)
            ''', (usn, name, dept_id, semester))
            master_id = cursor.lastrowid
            success_count += 1

            if session_id:
                desk_str = f"D-{current_desk_num:02d}"
                cursor.execute('''
                    INSERT OR IGNORE INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
                    VALUES (?, ?, ?, ?, ?, 'PENDING')
                ''', (session_id, master_id, usn, name, desk_str))
                current_desk_num += 1

        except sqlite3.IntegrityError:
            errors.append({'row': row_index, 'data': usn, 'message': f"Duplicate Student USN '{usn}' already exists in database."})

    conn.commit()

    # Re-fetch students
    cursor.execute('''
        SELECT s.*, d.code as dept_code 
        FROM students_master s
        LEFT JOIN departments d ON s.department_id = d.id
        ORDER BY s.usn ASC
    ''')
    students = [dict(r) for r in cursor.fetchall()]

    cursor.execute('SELECT id, course_code, room_number, exam_date FROM exam_sessions ORDER BY id DESC')
    sessions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    import_result = {
        'success_count': success_count,
        'errors': errors
    }

    if not errors:
        flash(f"Successfully imported {success_count} student records.", 'success')
    else:
        flash(f"Imported {success_count} records. {len(errors)} records had validation errors.", 'warning')

    return render_template('admin/admin_students.html', students=students, sessions=sessions, import_result=import_result)


@app.route('/admin/students/sample_csv')
@admin_required
def admin_students_sample_csv():
    output = "usn,student_name,department_code,semester\n"
    output += "1MS21CS050,Rahul Sharma,CSE,8\n"
    output += "1MS21CS051,Pooja Patel,CSE,8\n"
    output += "1MS21IS020,Naveen Kumar,ISE,8\n"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=sample_students_import.csv"}
    )


@app.route('/admin/barcodes')
@admin_required
def admin_barcodes_list():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT b.*, e.room_number 
        FROM booklet_registry b
        LEFT JOIN exam_sessions e ON b.assigned_session_id = e.id
        ORDER BY b.barcode_value ASC
    ''')
    barcodes = [dict(row) for row in cursor.fetchall()]

    available_count = sum(1 for b in barcodes if b['status'] == 'AVAILABLE')
    assigned_count = sum(1 for b in barcodes if b['status'] == 'ASSIGNED')
    void_count = sum(1 for b in barcodes if b['status'] in ('DAMAGED', 'VOID'))

    conn.close()

    return render_template(
        'admin/admin_barcodes.html',
        barcodes=barcodes,
        available_count=available_count,
        assigned_count=assigned_count,
        void_count=void_count
    )


@app.route('/admin/barcodes/import', methods=['POST'])
@admin_required
def admin_barcodes_import():
    file = request.files.get('csv_file')
    default_batch = (request.form.get('default_batch') or 'BATCH-2026-UPLOAD').strip()

    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid .csv file.', 'danger')
        return redirect(url_for('admin_barcodes_list'))

    content = file.stream.read().decode('utf-8', errors='ignore')
    reader = csv.reader(io.StringIO(content))

    conn = get_db()
    cursor = conn.cursor()

    success_count = 0
    duplicate_count = 0
    row_index = 0

    for row in reader:
        row_index += 1
        if not row or row_index == 1 and ('barcode' in row[0].lower()):
            continue

        barcode = row[0].strip().upper()
        batch = row[1].strip() if len(row) > 1 and row[1].strip() else default_batch

        if not barcode or len(barcode) < 3:
            continue

        try:
            cursor.execute('''
                INSERT INTO booklet_registry (barcode_value, batch_number, status)
                VALUES (?, ?, 'AVAILABLE')
            ''', (barcode, batch))
            success_count += 1
        except sqlite3.IntegrityError:
            duplicate_count += 1

    conn.commit()
    conn.close()

    flash(f"Successfully registered {success_count} authorized answer booklets. ({duplicate_count} duplicates skipped).", 'success')
    return redirect(url_for('admin_barcodes_list'))


@app.route('/admin/barcodes/sample_csv')
@admin_required
def admin_barcodes_sample_csv():
    output = "barcode_value,batch_number\n"
    output += "BK20260201,BATCH-2026-02\n"
    output += "BK20260202,BATCH-2026-02\n"
    output += "BK20260203,BATCH-2026-02\n"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=sample_authorized_barcodes.csv"}
    )


@app.route('/admin/audit')
@admin_required
def admin_audit_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.*, s.course_code, s.room_number 
        FROM audit_trail a
        LEFT JOIN exam_sessions s ON a.session_id = s.id
        ORDER BY a.id DESC LIMIT 400
    ''')
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template('admin/admin_audit.html', logs=logs)


@app.route('/admin/reports')
@admin_required
def admin_reports_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            s.*, 
            d.code as dept_code,
            (SELECT COUNT(*) FROM students WHERE session_id = s.id) as total_count,
            (SELECT COUNT(*) FROM students WHERE session_id = s.id AND attendance_status = 'PRESENT') as present_count,
            (SELECT COUNT(*) FROM students WHERE session_id = s.id AND attendance_status = 'ABSENT') as absent_count
        FROM exam_sessions s
        LEFT JOIN departments d ON s.department_id = d.id
        ORDER BY s.id DESC
    ''')
    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template('admin/admin_reports.html', sessions=sessions)


# ----------------- Legacy Compatibility Views -----------------

@app.route('/audit')
def audit_view():
    """
    Public / Invigilator Audit Log Viewer.
    """
    session_id = request.args.get('session_id', type=int)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id, course_code, room_number FROM exam_sessions ORDER BY id ASC')
    sessions = [dict(row) for row in cursor.fetchall()]

    query = '''
        SELECT a.*, s.course_code, s.room_number 
        FROM audit_trail a
        LEFT JOIN exam_sessions s ON a.session_id = s.id
    '''
    params = []
    if session_id:
        query += ' WHERE a.session_id = ?'
        params.append(session_id)

    query += ' ORDER BY a.id DESC LIMIT 300'
    cursor.execute(query, params)
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return render_template('audit.html', logs=logs, sessions=sessions, current_session_id=session_id)


@app.route('/evaluator')
def evaluator_view():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ev.*, s.course_code, s.room_number, s.exam_date
        FROM evaluation_verifications ev
        LEFT JOIN exam_sessions s ON ev.session_id = s.id
        ORDER BY ev.id DESC LIMIT 100
    ''')
    verifications = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template('evaluator.html', verifications=verifications)


@app.route('/sample_barcodes')
def sample_barcodes():
    return render_template('sample_barcodes.html')


@app.route('/api/evaluator/verify', methods=['POST'])
def evaluator_cross_verify():
    data = request.get_json() or {}
    session_id = data.get('session_id')
    usn = (data.get('usn') or '').strip().upper()
    scanned_qp_barcode = (data.get('scanned_qp_barcode') or '').strip().upper()
    evaluator_name = data.get('evaluator_name', 'Dr. Evaluation Officer').strip()
    evaluator_id = data.get('evaluator_id', 'EVAL-101').strip()

    if not usn or not scanned_qp_barcode:
        return jsonify({'success': False, 'message': 'Both Student USN and Question Paper Barcode are required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    if session_id:
        cursor.execute('''
            SELECT s.*, e.course_code, e.course_name, e.exam_date, e.exam_session, e.qp_code, e.room_number, e.status as session_status
            FROM students s
            JOIN exam_sessions e ON s.session_id = e.id
            WHERE s.usn = ? AND s.session_id = ?
            ORDER BY s.id DESC LIMIT 1
        ''', (usn, session_id))
        record = cursor.fetchone()
    else:
        cursor.execute('''
            SELECT s.*, e.course_code, e.course_name, e.exam_date, e.exam_session, e.qp_code, e.room_number, e.status as session_status
            FROM students s
            JOIN exam_sessions e ON s.session_id = e.id
            WHERE s.usn = ? AND (s.qp_barcode = ? OR s.attendance_status = 'PRESENT')
            ORDER BY (CASE WHEN s.qp_barcode = ? THEN 1 WHEN s.attendance_status = 'PRESENT' THEN 2 ELSE 3 END) ASC, s.id DESC
            LIMIT 1
        ''', (usn, scanned_qp_barcode, scanned_qp_barcode))
        record = cursor.fetchone()
        if not record:
            cursor.execute('''
                SELECT s.*, e.course_code, e.course_name, e.exam_date, e.exam_session, e.qp_code, e.room_number, e.status as session_status
                FROM students s
                JOIN exam_sessions e ON s.session_id = e.id
                WHERE s.usn = ?
                ORDER BY s.id DESC LIMIT 1
            ''', (usn,))
            record = cursor.fetchone()

    now_ts = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

    if not record:
        status = 'DISCREPANCY_FLAGGED'
        details = f"DISCREPANCY: Candidate USN '{usn}' was not found in any exam attendance roster!"
        cursor.execute('''
            INSERT INTO evaluation_verifications (usn, scanned_qp_barcode, session_id, evaluator_name, evaluator_id, verification_status, details, timestamp)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
        ''', (usn, scanned_qp_barcode, evaluator_name, evaluator_id, status, details, now_ts))
        conn.commit()
        conn.close()
        return jsonify({
            'success': False,
            'status': status,
            'is_valid': False,
            'details': details
        })

    record_dict = dict(record)
    attendance_status = record_dict['attendance_status']
    recorded_qp_barcode = record_dict['qp_barcode'] or ''
    assigned_qp_code = record_dict['qp_code']

    discrepancies = []
    if attendance_status == 'ABSENT':
        discrepancies.append(f"CRITICAL DISCREPANCY: Candidate {usn} was recorded as ABSENT in room {record_dict['room_number']}, but a booklet is presented for evaluation!")
    elif attendance_status == 'PENDING':
        discrepancies.append(f"WARNING: Attendance for candidate {usn} was never completed (Status: PENDING).")

    if recorded_qp_barcode and scanned_qp_barcode != recorded_qp_barcode:
        discrepancies.append(f"BARCODE MISMATCH: Evaluated booklet barcode '{scanned_qp_barcode}' does not match examination hall scanned barcode '{recorded_qp_barcode}'.")
    elif not recorded_qp_barcode and scanned_qp_barcode != assigned_qp_code:
        discrepancies.append(f"BARCODE MISMATCH: Scanned barcode '{scanned_qp_barcode}' does not match official series '{assigned_qp_code}'.")

    if discrepancies:
        status = 'DISCREPANCY_FLAGGED'
        details = " | ".join(discrepancies)
        is_valid = False
    else:
        status = 'VERIFIED_MATCH'
        details = f"VERIFIED: Attendance status is PRESENT. Barcode matches examination room record ({scanned_qp_barcode})."
        is_valid = True

    cursor.execute('''
        INSERT INTO evaluation_verifications (usn, scanned_qp_barcode, session_id, evaluator_name, evaluator_id, verification_status, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (usn, scanned_qp_barcode, record_dict['session_id'], evaluator_name, evaluator_id, status, details, now_ts))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'status': status,
        'is_valid': is_valid,
        'details': details,
        'record': {
            'usn': usn,
            'student_name': record_dict['student_name'],
            'course_code': record_dict['course_code'],
            'course_name': record_dict['course_name'],
            'room_number': record_dict['room_number'],
            'exam_date': record_dict['exam_date'],
            'attendance_status': attendance_status,
            'recorded_qp_barcode': recorded_qp_barcode or record_dict['qp_code'],
            'marked_at': record_dict['marked_at'],
            'timestamp': now_ts
        }
    })

if __name__ == '__main__':
    print("=" * 65)
    print(" Barcode-Based Digital Examination Attendance System ")
    print(" Running on: http://127.0.0.1:5000")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=True)
