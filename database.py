"""
Database layer for Digital Examination Attendance and Verification System.
Handles SQLite initialization, normalized schemas, role-based users,
departments, classrooms, exams, booklet barcode registry, and audit logging.
"""
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exam_attendance.db')

def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn

def ensure_column_exists(cursor, table_name, column_name, column_def):
    cursor.execute(f"PRAGMA table_info({table_name});")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def};")

def init_db(db_path=None):
    """
    Initializes the database schema with normalized relational tables and migrations.
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    # 1. Users table (Admins and Teachers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('ADMIN', 'TEACHER')),
        department_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    ''')

    # 2. Departments table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 3. Classrooms table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classrooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL,
        room_number TEXT NOT NULL,
        building TEXT,
        capacity INTEGER DEFAULT 40,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id),
        UNIQUE(department_id, room_number)
    )
    ''')

    # 4. Teacher Department Authorizations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teacher_department_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
        UNIQUE(user_id, department_id)
    )
    ''')

    # 5. Examinations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS examinations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_code TEXT UNIQUE NOT NULL,
        exam_name TEXT NOT NULL,
        academic_year TEXT NOT NULL,
        term TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 6. Subjects table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL,
        subject_code TEXT UNIQUE NOT NULL,
        subject_name TEXT NOT NULL,
        qp_code TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    ''')

    # 7. Exam Sessions table (Classroom session allocations)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exam_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        subject_id INTEGER,
        department_id INTEGER,
        classroom_id INTEGER,
        course_code TEXT NOT NULL,
        course_name TEXT NOT NULL,
        exam_date TEXT NOT NULL,
        exam_session TEXT NOT NULL,
        room_number TEXT NOT NULL,
        qp_code TEXT NOT NULL,
        invigilator_name TEXT NOT NULL,
        invigilator_id TEXT NOT NULL,
        invigilator_user_id INTEGER,
        status TEXT DEFAULT 'NOT_STARTED',
        locked_at TEXT,
        locked_by TEXT,
        submitted_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (exam_id) REFERENCES examinations(id),
        FOREIGN KEY (subject_id) REFERENCES subjects(id),
        FOREIGN KEY (department_id) REFERENCES departments(id),
        FOREIGN KEY (classroom_id) REFERENCES classrooms(id),
        FOREIGN KEY (invigilator_user_id) REFERENCES users(id)
    )
    ''')

    # 8. Master Students Catalog
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usn TEXT UNIQUE NOT NULL,
        student_name TEXT NOT NULL,
        department_id INTEGER,
        semester INTEGER DEFAULT 8,
        email TEXT,
        phone TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    ''')

    # 9. Session Students Roster (Assigned to exam sessions)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        student_master_id INTEGER,
        usn TEXT NOT NULL,
        student_name TEXT NOT NULL,
        desk_number TEXT NOT NULL,
        attendance_status TEXT DEFAULT 'PENDING' CHECK(attendance_status IN ('PENDING', 'PRESENT', 'ABSENT')),
        qp_barcode TEXT,
        marked_at TEXT,
        marked_by TEXT,
        FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_master_id) REFERENCES students_master(id),
        UNIQUE(session_id, usn)
    )
    ''')

    # 10. Authorized Answer Booklet Barcode Registry
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS booklet_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode_value TEXT UNIQUE NOT NULL,
        exam_id INTEGER,
        batch_number TEXT,
        status TEXT DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE', 'ASSIGNED', 'DAMAGED', 'VOID')),
        assigned_session_id INTEGER,
        assigned_usn TEXT,
        assigned_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (exam_id) REFERENCES examinations(id),
        FOREIGN KEY (assigned_session_id) REFERENCES exam_sessions(id)
    )
    ''')

    # 11. Digital Audit Trail table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_trail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        usn TEXT,
        student_name TEXT,
        action_type TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT,
        qp_barcode TEXT,
        reason TEXT,
        invigilator_id TEXT NOT NULL,
        invigilator_name TEXT,
        user_id INTEGER,
        timestamp TEXT NOT NULL,
        client_ip TEXT,
        FOREIGN KEY (session_id) REFERENCES exam_sessions(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # 12. Evaluator Cross-Verification table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evaluation_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usn TEXT NOT NULL,
        scanned_qp_barcode TEXT NOT NULL,
        session_id INTEGER,
        evaluator_name TEXT NOT NULL,
        evaluator_id TEXT NOT NULL,
        verification_status TEXT NOT NULL,
        details TEXT,
        timestamp TEXT NOT NULL
    )
    ''')

    # Safe Schema Migrations for existing tables
    ensure_column_exists(cursor, 'exam_sessions', 'exam_id', 'INTEGER')
    ensure_column_exists(cursor, 'exam_sessions', 'subject_id', 'INTEGER')
    ensure_column_exists(cursor, 'exam_sessions', 'department_id', 'INTEGER')
    ensure_column_exists(cursor, 'exam_sessions', 'classroom_id', 'INTEGER')
    ensure_column_exists(cursor, 'exam_sessions', 'invigilator_user_id', 'INTEGER')
    ensure_column_exists(cursor, 'exam_sessions', 'submitted_at', 'TEXT')
    ensure_column_exists(cursor, 'students', 'student_master_id', 'INTEGER')
    ensure_column_exists(cursor, 'audit_trail', 'user_id', 'INTEGER')

    conn.commit()
    conn.close()

def log_audit(session_id, action_type, invigilator_id, invigilator_name, usn=None, student_name=None,
              old_status=None, new_status=None, qp_barcode=None, reason=None, client_ip="127.0.0.1",
              user_id=None, cursor=None):
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    insert_sql = '''
    INSERT INTO audit_trail (
        session_id, usn, student_name, action_type, old_status, new_status,
        qp_barcode, reason, invigilator_id, invigilator_name, user_id, timestamp, client_ip
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (session_id, usn, student_name, action_type, old_status, new_status,
              qp_barcode, reason, invigilator_id, invigilator_name, user_id, now_ts, client_ip)

    if cursor:
        cursor.execute(insert_sql, params)
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute(insert_sql, params)
        conn.commit()
        conn.close()

def seed_demo_data(db_path=None):
    conn = get_db(db_path)
    cursor = conn.cursor()

    # 1. Seed Departments
    cursor.execute('SELECT COUNT(*) FROM departments')
    if cursor.fetchone()[0] == 0:
        departments = [
            ('CSE', 'Computer Science and Engineering'),
            ('ISE', 'Information Science and Engineering'),
            ('ECE', 'Electronics and Communication Engineering'),
            ('EEE', 'Electrical and Electronics Engineering'),
            ('ME', 'Mechanical Engineering'),
            ('CV', 'Civil Engineering')
        ]
        cursor.executemany('INSERT INTO departments (code, name) VALUES (?, ?)', departments)
        conn.commit()

    # Fetch Department IDs
    cursor.execute('SELECT id, code FROM departments')
    dept_map = {row['code']: row['id'] for row in cursor.fetchall()}

    # 2. Seed Classrooms
    cursor.execute('SELECT COUNT(*) FROM classrooms')
    if cursor.fetchone()[0] == 0:
        classrooms = [
            (dept_map.get('CSE'), 'Room 302 (Block B)', 'Block B', 40),
            (dept_map.get('CSE'), 'Room 304 (Block B)', 'Block B', 40),
            (dept_map.get('ISE'), 'Room 405 (Block C)', 'Block C', 35),
            (dept_map.get('ECE'), 'Room 201 (Block A)', 'Block A', 45),
            (dept_map.get('ME'),  'Room 101 (Block D)', 'Block D', 30),
            (dept_map.get('CV'),  'Room 102 (Block D)', 'Block D', 30),
        ]
        cursor.executemany('INSERT INTO classrooms (department_id, room_number, building, capacity) VALUES (?, ?, ?, ?)', classrooms)
        conn.commit()

    # Fetch Classroom IDs
    cursor.execute('SELECT id, room_number FROM classrooms')
    room_map = {row['room_number']: row['id'] for row in cursor.fetchall()}

    # 3. Seed Users (Admin and Teachers)
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        admin_pass = generate_password_hash('AdminPassword@2026')
        cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
        VALUES ('admin', 'admin@college.edu', ?, 'System Administrator (COE Office)', 'ADMIN', NULL, 1)
        ''', (admin_pass,))
        admin_id = cursor.lastrowid

        teacher0_pass = generate_password_hash('TeacherPass@2026')
        cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
        VALUES ('teachername', 'teacher@college.edu', ?, 'Faculty Invigilator', 'TEACHER', ?, 1)
        ''', (teacher0_pass, dept_map.get('CSE')))
        t0_id = cursor.lastrowid

        teacher1_pass = generate_password_hash('TeacherPass@2026')
        cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
        VALUES ('teacherramesh', 'ramesh.sharma@college.edu', ?, 'Dr. Ramesh Sharma', 'TEACHER', ?, 1)
        ''', (teacher1_pass, dept_map.get('CSE')))
        t1_id = cursor.lastrowid

        teacher2_pass = generate_password_hash('TeacherPass@2026')
        cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
        VALUES ('teacherpriya', 'priya.v@college.edu', ?, 'Prof. Priya Venkatesh', 'TEACHER', ?, 1)
        ''', (teacher2_pass, dept_map.get('ISE')))
        t2_id = cursor.lastrowid

        teacher3_pass = generate_password_hash('TeacherPass@2026')
        cursor.execute('''
        INSERT INTO users (username, email, password_hash, full_name, role, department_id, is_active)
        VALUES ('teacherarun', 'arun.kumar@college.edu', ?, 'Prof. Arun Kumar', 'TEACHER', ?, 1)
        ''', (teacher3_pass, dept_map.get('ECE')))
        t3_id = cursor.lastrowid

        for d_id in dept_map.values():
            cursor.execute('INSERT OR IGNORE INTO teacher_department_access (user_id, department_id) VALUES (?, ?)', (t0_id, d_id))
        cursor.execute('INSERT INTO teacher_department_access (user_id, department_id) VALUES (?, ?)', (t1_id, dept_map.get('CSE')))
        cursor.execute('INSERT INTO teacher_department_access (user_id, department_id) VALUES (?, ?)', (t2_id, dept_map.get('ISE')))
        cursor.execute('INSERT INTO teacher_department_access (user_id, department_id) VALUES (?, ?)', (t3_id, dept_map.get('ECE')))
        conn.commit()

    # 4. Seed Examination & Subjects
    cursor.execute('SELECT COUNT(*) FROM examinations')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
        INSERT INTO examinations (exam_code, exam_name, academic_year, term)
        VALUES ('EXAM-2026-EVEN', 'Bachelor of Engineering Semester End Examination', '2025-2026', 'EVEN')
        ''')
        exam_id = cursor.lastrowid

        subjects = [
            (dept_map.get('CSE'), 'CS801', 'Cloud Computing & Distributed Systems', 'QP-2026-CS801-A'),
            (dept_map.get('ISE'), 'IS702', 'Machine Learning & Neural Networks', 'QP-2026-IS702-B'),
            (dept_map.get('ECE'), 'EC603', 'Digital Signal Processing & VLSI', 'QP-2026-EC603-C'),
        ]
        cursor.executemany('INSERT INTO subjects (department_id, subject_code, subject_name, qp_code) VALUES (?, ?, ?, ?)', subjects)
        conn.commit()
    else:
        cursor.execute('SELECT id FROM examinations LIMIT 1')
        exam_id = cursor.fetchone()[0]

    # 5. Seed Exam Sessions
    cursor.execute('SELECT COUNT(*) FROM exam_sessions')
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d")

        cursor.execute('''
        INSERT INTO exam_sessions (
            exam_id, department_id, classroom_id, course_code, course_name, exam_date,
            exam_session, room_number, qp_code, invigilator_name, invigilator_id, status
        ) VALUES (
            ?, ?, ?, 'CS801', 'Cloud Computing & Distributed Systems', ?,
            'Morning (09:30 AM - 12:30 PM)', 'Room 302 (Block B)', 'QP-2026-CS801-A',
            'Dr. Ramesh Sharma', 'INV-104', 'IN_PROGRESS'
        )
        ''', (exam_id, dept_map.get('CSE'), room_map.get('Room 302 (Block B)'), now_str))
        session_id_1 = cursor.lastrowid

        sample_students_1 = [
            ("1MS21CS001", "Aakash Verma", "D-01"),
            ("1MS21CS002", "Ananya Hegde", "D-02"),
            ("1MS21CS003", "Bhavik Patel", "D-03"),
            ("1MS21CS004", "Deepak Kumar", "D-04"),
            ("1MS21CS005", "Divya Suresh", "D-05"),
            ("1MS21CS006", "Farhan Ahmed", "D-06"),
            ("1MS21CS007", "Ishaan Malhotra", "D-07"),
            ("1MS21CS008", "Kavya Nair", "D-08"),
            ("1MS21CS009", "Manish Rao", "D-09"),
            ("1MS21CS010", "Neha Kulkarni", "D-10"),
            ("1MS21CS011", "Pranav Joshi", "D-11"),
            ("1MS21CS012", "Pooja Hegde", "D-12"),
            ("1MS21CS013", "Rahul Sundaram", "D-13"),
            ("1MS21CS014", "Sneha Reddy", "D-14"),
            ("1MS21CS015", "Varun Bhat", "D-15"),
        ]
        for usn, name, desk in sample_students_1:
            cursor.execute('''
            INSERT OR IGNORE INTO students_master (usn, student_name, department_id)
            VALUES (?, ?, ?)
            ''', (usn, name, dept_map.get('CSE')))
            master_id = cursor.lastrowid

            cursor.execute('''
            INSERT INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            ''', (session_id_1, master_id, usn, name, desk))

        cursor.execute('''
        INSERT INTO exam_sessions (
            exam_id, department_id, classroom_id, course_code, course_name, exam_date,
            exam_session, room_number, qp_code, invigilator_name, invigilator_id, status
        ) VALUES (
            ?, ?, ?, 'IS702', 'Machine Learning & Neural Networks', ?,
            'Afternoon (02:00 PM - 05:00 PM)', 'Room 405 (Block C)', 'QP-2026-IS702-B',
            'Prof. Priya Venkatesh', 'INV-208', 'IN_PROGRESS'
        )
        ''', (exam_id, dept_map.get('ISE'), room_map.get('Room 405 (Block C)'), now_str))
        session_id_2 = cursor.lastrowid

        sample_students_2 = [
            ("1MS21IS001", "Aditya Sen", "D-01"),
            ("1MS21IS002", "Chirag Shah", "D-02"),
            ("1MS21IS003", "Gautam Iyer", "D-03"),
            ("1MS21IS004", "Harshita Das", "D-04"),
            ("1MS21IS005", "Kiran George", "D-05"),
        ]
        for usn, name, desk in sample_students_2:
            cursor.execute('''
            INSERT OR IGNORE INTO students_master (usn, student_name, department_id)
            VALUES (?, ?, ?)
            ''', (usn, name, dept_map.get('ISE')))
            master_id = cursor.lastrowid

            cursor.execute('''
            INSERT INTO students (session_id, student_master_id, usn, student_name, desk_number, attendance_status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            ''', (session_id_2, master_id, usn, name, desk))

        # Seed additional subject exams for Room 302: Mathematics, DSA, ADLD, QCE
        additional_room302_subjects = [
            ('MAT301', 'Advanced Engineering Mathematics', 'Afternoon (02:00 PM - 05:00 PM)', 'QP-2026-MAT301-A'),
            ('CS302', 'Data Structures & Algorithms (DSA)', 'Morning (09:30 AM - 12:30 PM)', 'QP-2026-CS302-A'),
            ('EC303', 'Analog & Digital Logic Design (ADLD)', 'Afternoon (02:00 PM - 05:00 PM)', 'QP-2026-EC303-A'),
            ('QC401', 'Quantum Computing & Engineering (QCE)', 'Morning (09:30 AM - 12:30 PM)', 'QP-2026-QC401-A'),
        ]
        for c_code, c_name, c_sess, c_qp in additional_room302_subjects:
            cursor.execute('''
            INSERT INTO exam_sessions (
                exam_id, department_id, classroom_id, course_code, course_name, exam_date,
                exam_session, room_number, qp_code, invigilator_name, invigilator_id, status
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, 'Room 302 (Block B)', ?,
                'Dr. Ramesh Sharma', 'INV-104', 'IN_PROGRESS'
            )
            ''', (exam_id, dept_map.get('CSE'), room_map.get('Room 302 (Block B)'), c_code, c_name, now_str, c_sess, c_qp))
            sub_sess_id = cursor.lastrowid
            clone_roster_for_new_session(session_id_1, sub_sess_id, cursor=cursor)

        conn.commit()

    # Backfill migration data for any pre-existing sessions
    cursor.execute("UPDATE exam_sessions SET department_id = (SELECT id FROM departments WHERE code = 'CSE') WHERE department_id IS NULL AND (course_code LIKE 'CS%' OR room_number LIKE '%302%')")
    cursor.execute("UPDATE exam_sessions SET department_id = (SELECT id FROM departments WHERE code = 'ISE') WHERE department_id IS NULL AND (course_code LIKE 'IS%' OR room_number LIKE '%405%')")
    cursor.execute("UPDATE exam_sessions SET classroom_id = (SELECT id FROM classrooms WHERE classrooms.room_number = exam_sessions.room_number) WHERE classroom_id IS NULL")
    conn.commit()

    # Ensure Room 302 has multiple subjects scheduled (Mathematics, DSA, ADLD, QCE)
    cursor.execute("SELECT COUNT(*) FROM exam_sessions WHERE course_code = 'MAT301'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT id FROM exam_sessions WHERE course_code = 'CS801' LIMIT 1")
        base_s = cursor.fetchone()
        if base_s:
            base_id = base_s[0]
            now_str = datetime.now().strftime("%Y-%m-%d")
            additional_subjects = [
                ('MAT301', 'Advanced Engineering Mathematics', 'Afternoon (02:00 PM - 05:00 PM)', 'QP-2026-MAT301-A'),
                ('CS302', 'Data Structures & Algorithms (DSA)', 'Morning (09:30 AM - 12:30 PM)', 'QP-2026-CS302-A'),
                ('EC303', 'Analog & Digital Logic Design (ADLD)', 'Afternoon (02:00 PM - 05:00 PM)', 'QP-2026-EC303-A'),
                ('QC401', 'Quantum Computing & Engineering (QCE)', 'Morning (09:30 AM - 12:30 PM)', 'QP-2026-QC401-A'),
            ]
            for c_code, c_name, c_sess, c_qp in additional_subjects:
                cursor.execute('''
                INSERT INTO exam_sessions (
                    exam_id, department_id, classroom_id, course_code, course_name, exam_date,
                    exam_session, room_number, qp_code, invigilator_name, invigilator_id, status
                ) VALUES (
                    ?, (SELECT id FROM departments WHERE code='CSE'),
                    (SELECT id FROM classrooms WHERE room_number LIKE '%302%' LIMIT 1),
                    ?, ?, ?, ?, 'Room 302 (Block B)', ?, 'Dr. Ramesh Sharma', 'INV-104', 'IN_PROGRESS'
                )
                ''', (exam_id, c_code, c_name, now_str, c_sess, c_qp))
                new_s_id = cursor.lastrowid
                clone_roster_for_new_session(base_id, new_s_id, cursor=cursor)
            conn.commit()

    # 6. Seed Authorized Booklet Barcode Registry
    cursor.execute('SELECT COUNT(*) FROM booklet_registry')
    if cursor.fetchone()[0] == 0:
        barcodes_to_register = []
        for i in range(1, 251):
            val = f"BK2026{i:04d}"
            barcodes_to_register.append((val, exam_id, 'BATCH-2026-01', 'AVAILABLE'))

        # Subject QP Series
        barcodes_to_register.append(('QP-2026-CS801-A', exam_id, 'QP-SERIES-CS801', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-MAT301-A', exam_id, 'QP-SERIES-MAT301', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-CS302-A', exam_id, 'QP-SERIES-CS302', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-EC303-A', exam_id, 'QP-SERIES-EC303', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-QC401-A', exam_id, 'QP-SERIES-QC401', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-IS702-B', exam_id, 'QP-SERIES-IS702', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-SERIES-A', exam_id, 'QP-SERIES-A', 'AVAILABLE'))
        barcodes_to_register.append(('QP-2026-SERIES-B', exam_id, 'QP-SERIES-B', 'AVAILABLE'))

        cursor.executemany('''
        INSERT OR IGNORE INTO booklet_registry (barcode_value, exam_id, batch_number, status)
        VALUES (?, ?, ?, ?)
        ''', barcodes_to_register)
        conn.commit()

    conn.close()

def clone_roster_for_new_session(source_session_id, target_session_id, cursor=None):
    """
    Copies all assigned candidates from source_session_id to target_session_id
    with fresh PENDING status and cleared barcodes, so the teacher NEVER has to
    re-import or re-type student rosters for subsequent subjects in the same hall.
    """
    should_close = False
    if not cursor:
        conn = get_db()
        cursor = conn.cursor()
        should_close = True

    cursor.execute('''
        SELECT student_master_id, usn, student_name, desk_number 
        FROM students 
        WHERE session_id = ? 
        ORDER BY desk_number ASC
    ''', (source_session_id,))
    students = cursor.fetchall()

    for s in students:
        cursor.execute('''
            INSERT OR IGNORE INTO students (
                session_id, student_master_id, usn, student_name, desk_number, attendance_status
            ) VALUES (?, ?, ?, ?, ?, 'PENDING')
        ''', (target_session_id, s['student_master_id'], s['usn'], s['student_name'], s['desk_number']))

    if should_close:
        conn.commit()
        conn.close()
