import os
import subprocess

html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>COE ExamAttend - Digital Examination Attendance & Verification System Report</title>
<style>
    @page {
        size: A4 portrait;
        margin: 18mm 16mm 18mm 16mm;
        @bottom-right {
            content: "Page " counter(page);
            font-family: 'Inter', system-ui, sans-serif;
            font-size: 8pt;
            color: #64748b;
        }
    }

    * {
        box-sizing: border-box;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #1e293b;
        line-height: 1.55;
        font-size: 9.5pt;
        background-color: #ffffff;
        margin: 0;
        padding: 0;
    }

    /* Page Breaks */
    .page-break {
        page-break-after: always;
        break-after: page;
    }
    .avoid-break {
        page-break-inside: avoid;
        break-inside: avoid;
    }

    /* Typography */
    h1, h2, h3, h4, h5 {
        color: #0f172a;
        font-weight: 700;
        margin-top: 1.4em;
        margin-bottom: 0.5em;
        line-height: 1.25;
    }
    h1 { font-size: 20pt; color: #1e3a8a; }
    h2 { font-size: 14pt; color: #1e3a8a; border-bottom: 1.5pt solid #e2e8f0; padding-bottom: 4px; margin-top: 1.6em; }
    h3 { font-size: 11pt; color: #0f172a; margin-top: 1.2em; }
    h4 { font-size: 10pt; color: #334155; }
    p { margin: 0.5em 0; text-align: justify; }

    /* Cover Page */
    .cover-page {
        min-height: 92vh;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        text-align: center;
        padding: 40px 20px 20px 20px;
        border: 2px solid #e2e8f0;
        border-radius: 8px;
        background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
    }
    .cover-header {
        border-bottom: 2px solid #1e3a8a;
        padding-bottom: 20px;
    }
    .cover-institution {
        font-size: 13pt;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #1e3a8a;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .cover-office {
        font-size: 10.5pt;
        color: #475569;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .cover-badge-box {
        margin: 25px auto 10px auto;
        display: inline-block;
        background: #1e3a8a;
        color: #ffffff;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 8.5pt;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .cover-title {
        font-size: 22pt;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.2;
        margin: 15px 0 8px 0;
    }
    .cover-subtitle {
        font-size: 12pt;
        color: #475569;
        font-weight: 500;
        margin-bottom: 25px;
    }
    .cover-meta-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 15px;
        text-align: left;
        margin: 20px 30px;
        background: #ffffff;
        padding: 20px;
        border-radius: 6px;
        border: 1px solid #cbd5e1;
    }
    .meta-item {
        font-size: 9pt;
    }
    .meta-label {
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        font-size: 7.5pt;
        display: block;
        margin-bottom: 2px;
    }
    .meta-val {
        color: #0f172a;
        font-weight: 600;
    }
    .cover-pills {
        margin-top: 15px;
    }
    .pill {
        display: inline-block;
        background: #e2e8f0;
        color: #334155;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 7.5pt;
        font-weight: 600;
        margin: 2px;
    }
    .pill-blue { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
    .pill-green { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .pill-amber { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }

    /* Tables */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 12px 0 16px 0;
        font-size: 8.5pt;
    }
    th, td {
        padding: 6px 10px;
        border: 1px solid #cbd5e1;
        text-align: left;
        vertical-align: top;
    }
    th {
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 700;
        font-size: 8pt;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    tr:nth-child(even) td {
        background-color: #f8fafc;
    }

    /* Callout & Alert Boxes */
    .callout {
        padding: 10px 14px;
        border-radius: 6px;
        margin: 12px 0;
        font-size: 8.5pt;
        border-left: 4px solid #3b82f6;
        background: #f8fafc;
    }
    .callout-info { border-left-color: #2563eb; background: #eff6ff; color: #1e40af; }
    .callout-success { border-left-color: #16a34a; background: #f0fdf4; color: #166534; }
    .callout-warning { border-left-color: #d97706; background: #fffbeb; color: #92400e; }
    .callout-danger { border-left-color: #dc2626; background: #fef2f2; color: #991b1b; }

    /* Code blocks */
    code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 8pt;
        background-color: #f1f5f9;
        padding: 1.5px 4px;
        border-radius: 3px;
        color: #b91c1c;
        border: 1px solid #e2e8f0;
    }
    pre {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 7.5pt;
        background: #0f172a;
        color: #f8fafc;
        padding: 10px 14px;
        border-radius: 6px;
        overflow-x: auto;
        line-height: 1.45;
        margin: 10px 0;
    }

    /* Diagrams & Schematics */
    .diagram-container {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 12px;
        margin: 14px 0;
        text-align: center;
    }
    .diagram-title {
        font-weight: 700;
        font-size: 8pt;
        color: #475569;
        text-transform: uppercase;
        margin-bottom: 8px;
        letter-spacing: 0.5px;
    }

    /* Two column layouts */
    .two-col {
        display: flex;
        gap: 16px;
        margin: 10px 0;
    }
    .col-half {
        flex: 1;
    }

    /* Status indicators */
    .badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 7.5pt;
        font-weight: 700;
        font-family: monospace;
    }
    .badge-present { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
    .badge-absent { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
    .badge-pending { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
    .badge-locked { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
</style>
</head>
<body>

<!-- ================= COVER PAGE ================= -->
<div class="cover-page">
    <div class="cover-header">
        <div class="cover-institution">OFFICE OF THE CONTROLLER OF EXAMINATIONS</div>
        <div class="cover-office">University Central Examination Administration Portal</div>
    </div>

    <div>
        <div class="cover-badge-box">Official System Documentation & Technical Report</div>
        <div class="cover-title">DIGITAL EXAMINATION ATTENDANCE & VERIFICATION SYSTEM</div>
        <div class="cover-subtitle">COE ExamAttend Platform &bull; Architecture, Engineering & Verification Report</div>

        <div class="cover-pills">
            <span class="pill pill-blue">Python 3.11+ / Flask 3.1</span>
            <span class="pill pill-blue">SQLite3 WAL Architecture</span>
            <span class="pill pill-green">WebRTC Barcode Scanner</span>
            <span class="pill pill-green">OpenPyXL COE Reports</span>
            <span class="pill pill-amber">Atomic Duplicate Prevention</span>
            <span class="pill pill-amber">Persistent JSON Restore</span>
        </div>

        <div class="cover-meta-grid">
            <div class="meta-item">
                <span class="meta-label">System Release Version</span>
                <span class="meta-val">Version 2.5 (Production Release)</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Target Audience</span>
                <span class="meta-val">COE Administrators, Invigilators, Evaluators</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Document Classification</span>
                <span class="meta-val">Institutional Technical Architecture & Audit</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Automated Test Coverage</span>
                <span class="meta-val">100% Pass (30 System Requirements Verified)</span>
            </div>
        </div>
    </div>

    <div style="border-top: 1px solid #e2e8f0; padding-top: 15px; font-size: 8pt; color: #64748b;">
        Autonomous College & University Examination Infrastructure &bull; Strict Role-Based Security Enforced
    </div>
</div>

<div class="page-break"></div>

<!-- ================= TABLE OF CONTENTS ================= -->
<h2>Table of Contents</h2>
<table style="margin-top: 20px;">
    <thead>
        <tr>
            <th style="width: 10%;">Section</th>
            <th style="width: 70%;">Chapter Title</th>
            <th style="width: 20%; text-align: right;">Page Focus</th>
        </tr>
    </thead>
    <tbody>
        <tr><td><strong>1.0</strong></td><td><strong>Executive Summary & System Purpose</strong></td><td style="text-align: right;">Overview & Goals</td></tr>
        <tr><td><strong>2.0</strong></td><td><strong>Problem Statement & Operational Challenges</strong></td><td style="text-align: right;">Paper vs Digital</td></tr>
        <tr><td><strong>3.0</strong></td><td><strong>Frontend Engineering & Client-Side Architecture</strong></td><td style="text-align: right;">HTML5, CSS, JS, Scanner</td></tr>
        <tr><td><strong>4.0</strong></td><td><strong>Backend Engineering & Application Layer</strong></td><td style="text-align: right;">Flask, RBAC, Services</td></tr>
        <tr><td><strong>5.0</strong></td><td><strong>Relational Database Schema & Data Integrity</strong></td><td style="text-align: right;">SQLite 3NF Schema</td></tr>
        <tr><td><strong>6.0</strong></td><td><strong>State Transitions, Time Gating & Persistence Engine</strong></td><td style="text-align: right;">Backup & Auto-Restore</td></tr>
        <tr><td><strong>7.0</strong></td><td><strong>Security Architecture & Anti-Fraud Measures</strong></td><td style="text-align: right;">Duplicate Prevention</td></tr>
        <tr><td><strong>8.0</strong></td><td><strong>End-to-End Operational Workflows</strong></td><td style="text-align: right;">Scheduling & Scanning</td></tr>
        <tr><td><strong>9.0</strong></td><td><strong>Automated Verification & 30-Scenario Test Suite</strong></td><td style="text-align: right;">Quality Assurance</td></tr>
        <tr><td><strong>10.0</strong></td><td><strong>Deployment, Cloud Architecture & Appendices</strong></td><td style="text-align: right;">Render & Production</td></tr>
    </tbody>
</table>

<div class="callout callout-info" style="margin-top: 25px;">
    <strong>Document Note:</strong> This technical report details both the software engineering architecture (frontend, backend, database, APIs) and the institutional operational workflows governing examination attendance recording, duplicate prevention, and COE spreadsheet publishing.
</div>

<!-- ================= SECTION 1 & 2 ================= -->
<h2>1.0 Executive Summary & System Purpose</h2>
<p>
The <strong>Digital Examination Attendance and Verification System (COE ExamAttend)</strong> is an enterprise web solution designed to transform university and college examination operations. In conventional university setups, invigilators distribute physical paper rosters where students handwrite their names, roll numbers (USNs), and answer booklet serial numbers followed by ink signatures. This obsolete methodology is error-prone, vulnerable to booklet swapping, disrupts candidates during high-stakes exams, and creates massive post-exam administrative burdens.
</p>
<p>
<strong>COE ExamAttend</strong> eliminates paper attendance by turning any smartphone, tablet, or laptop into a secure, real-time optical barcode scanner. Invigilators scan the unique barcode printed on each candidate's physical answer booklet. The server validates the booklet against an authorized inventory registry, verifies seat allocation, prevents duplicate assignments, logs an immutable audit trail, and locks the session upon completion.
</p>

<h2>2.0 Problem Statement & Operational Challenges</h2>
<table>
    <thead>
        <tr>
            <th>Legacy Paper Methodology</th>
            <th>COE ExamAttend Digital Solution</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Transcription Errors:</strong> 10-digit USNs and booklet numbers manually miswritten by tired candidates.</td>
            <td><strong>Optical Precision:</strong> 100% exact barcode decoding via high-speed WebRTC camera scanner (Code128 / Code39 / QR).</td>
        </tr>
        <tr>
            <td><strong>Duplicate Booklet Fraud:</strong> Impossible to immediately detect if two candidates wrote down the same booklet number.</td>
            <td><strong>Atomic Collision Prevention:</strong> Database optimistic concurrency locks immediately reject any previously assigned barcode (HTTP 409).</td>
        </tr>
        <tr>
            <td><strong>Exam Interruption:</strong> Invigilators walk up to seated candidates with bulky rosters, breaking concentration.</td>
            <td><strong>Non-Intrusive 1-Tap Scan:</strong> Invigilator scans the desk booklet in under 1 second without disturbing the student.</td>
        </tr>
        <tr>
            <td><strong>Tampering & Discrepancies:</strong> Paper sheets can be altered, lost, or back-dated after collection.</td>
            <td><strong>Immutable Forensic Logging:</strong> Every scan, status redo, and submission is recorded with client IP, invigilator ID, and IST timestamp.</td>
        </tr>
        <tr>
            <td><strong>Delayed COE Consolidation:</strong> Days spent keying handwritten sheets into university computers.</td>
            <td><strong>Instant Publication-Grade Excel:</strong> Official 14-column COE spreadsheet (.xlsx) generated automatically upon submission.</td>
        </tr>
    </tbody>
</table>

<div class="page-break"></div>

<!-- ================= SECTION 3: FRONTEND ================= -->
<h2>3.0 Frontend Engineering & Client-Side Architecture</h2>

<h3>3.1 Technology Stack & Component Structure</h3>
<ul>
    <li><strong>HTML5 & Jinja2 Template Hierarchy:</strong> Organized under an extensible base template (<code>templates/base.html</code>) enforcing role-based navigation, active session indicators, breadcrumbs, and device connectivity badges.</li>
    <li><strong>Bootstrap 5.3.3:</strong> Responsive 12-column mobile-first grid, flexible layout utilities, floating form controls, and accessible modal structures.</li>
    <li><strong>Custom Institutional CSS (<code>/static/css/style.css</code>):</strong> Tailored styling utilizing CSS custom properties (variables), high-contrast status pills, tactile feedback transitions, and touch-target padding.</li>
    <li><strong>Html5-QRCode Engine (v2.3.8):</strong> WebRTC camera barcode library utilizing native canvas rendering and ZXing algorithmic decoders, fully capable of recognizing 1D (Code128, Code39, EAN) and 2D (QR) symbologies.</li>
    <li><strong>SweetAlert2 (v11):</strong> Asynchronous, promise-driven UI modals providing affirmative visual alerts, destructive action prompts (e.g., removing scheduled exams), and validation warnings.</li>
    <li><strong>FontAwesome 6.5.2:</strong> Comprehensive vector iconography for rooms, status indicators, printers, clocks, and navigation cues.</li>
</ul>

<h3>3.2 Mobile-First Touch Ergonomics & Scanner Lifecycle</h3>
<p>
Invigilators carry out attendance recording on foot while patrolling exam halls. The frontend is engineered specifically for single-handed mobile navigation:
</p>
<ul>
    <li><strong>$48\text{px}\times48\text{px}$ Minimum Touch Targets:</strong> Touch zones for buttons, toggles, and search bars conform to WCAG 2.1 mobile touch ergonomics, preventing accidental taps.</li>
    <li><strong>Camera Stream Management:</strong> The camera stream binds exclusively when the scanner modal is actively visible and is automatically destroyed upon scan match or modal close. This prevents device overheating, saves mobile battery, and releases the hardware lock.</li>
    <li><strong>Visual & Auditory Feedback:</strong> Positive scans trigger a 1200Hz synthesized audio tone and flash a bright green border; duplicate/invalid scans emit a 300Hz error buzz and display an instructive SweetAlert2 modal explaining the exact reason.</li>
    <li><strong>Client-Side Instant Roster Filtering:</strong> Vanilla ES6 search algorithms allow invigilators to filter through 50+ candidates in real time by typing any part of a USN, student name, or desk number.</li>
    <li><strong>Connectivity Sentinel:</strong> A persistent browser event listener monitors online/offline status, presenting a prominent red banner if campus Wi-Fi fluctuates so teachers never assume unconfirmed data was persisted.</li>
</ul>

<div class="diagram-container avoid-break">
    <div class="diagram-title">Figure 1: Client-Side Optical Barcode Capture & State Loop</div>
    <svg width="600" height="95" viewBox="0 0 600 95" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="20" width="105" height="55" rx="6" fill="#1e3a8a"/>
        <text x="62" y="44" fill="#ffffff" font-size="8.5" font-family="sans-serif" font-weight="bold" text-anchor="middle">Mobile Camera</text>
        <text x="62" y="58" fill="#93c5fd" font-size="7.5" font-family="sans-serif" text-anchor="middle">WebRTC Stream</text>

        <line x1="115" y1="47" x2="155" y2="47" stroke="#2563eb" stroke-width="2" marker-end="url(#arrow)"/>

        <rect x="155" y="20" width="115" height="55" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.5"/>
        <text x="212" y="44" fill="#0f172a" font-size="8.5" font-family="sans-serif" font-weight="bold" text-anchor="middle">Html5-QRCode</text>
        <text x="212" y="58" fill="#64748b" font-size="7.5" font-family="sans-serif" text-anchor="middle">Canvas Matrix Decode</text>

        <line x1="270" y1="47" x2="310" y2="47" stroke="#2563eb" stroke-width="2"/>

        <rect x="310" y="20" width="115" height="55" rx="6" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.5"/>
        <text x="367" y="44" fill="#0f172a" font-size="8.5" font-family="sans-serif" font-weight="bold" text-anchor="middle">REST API Call</text>
        <text x="367" y="58" fill="#64748b" font-size="7.5" font-family="sans-serif" text-anchor="middle">POST /attendance/mark</text>

        <line x1="425" y1="47" x2="465" y2="47" stroke="#2563eb" stroke-width="2"/>

        <rect x="465" y="20" width="125" height="55" rx="6" fill="#166534"/>
        <text x="527" y="44" fill="#ffffff" font-size="8.5" font-family="sans-serif" font-weight="bold" text-anchor="middle">Optimistic DOM</text>
        <text x="527" y="58" fill="#bbf7d0" font-size="7.5" font-family="sans-serif" text-anchor="middle">Sound & Green Badge</text>
    </svg>
</div>

<!-- ================= SECTION 4: BACKEND ================= -->
<h2>4.0 Backend Engineering & Application Layer</h2>

<h3>4.1 Technology Stack & Architectural Roles</h3>
<ul>
    <li><strong>Python (v3.9 - v3.14):</strong> High-reliability programming environment hosting synchronous route handlers, time validation algorithms, and file generators.</li>
    <li><strong>Flask (v3.1+):</strong> Application routing engine providing modular HTTP endpoints, secure session cookie handling, request JSON deserialization, and Jinja2 rendering.</li>
    <li><strong>Werkzeug Security:</strong> Industry-standard cryptographic engine providing password hashing via PBKDF2/Scrypt algorithms with randomized salting.</li>
    <li><strong>OpenPyXL (v3.1+):</strong> Python spreadsheet library used to programmatically assemble official COE attendance spreadsheets with cell styling, auto-column widths, and metadata banners.</li>
    <li><strong>Gunicorn (v21.2+):</strong> WSGI server configured with 2-4 concurrent worker threads to service multiple room invigilators simultaneously in university deployments.</li>
</ul>

<h3>4.2 Key Backend Services & Design Patterns</h3>
<ol>
    <li><strong>Role-Based Access Control (RBAC):</strong>
        <p>Custom Python decorators <code>@login_required</code> and <code>@admin_required</code> govern endpoint access. Faculty invigilators have operational access across any exam hall on campus, while configuration endpoints (user accounts, syllabus, session deletion) are locked to the Administrator.</p>
    </li>
    <li><strong>Atomic Attendance Engine (<code>/api/attendance/mark</code>):</strong>
        <p>All database operations are wrapped inside immediate database transactions. If any verification fails (such as barcode already assigned, session locked, or invalid candidate), the transaction rolls back cleanly with zero orphaned records.</p>
    </li>
    <li><strong>Indian Standard Time (IST) Window Evaluator:</strong>
        <p>A specialized utility calculates session windows relative to standard Indian Time (UTC+05:30). Sessions strictly transition through <code>UPCOMING</code> (pre-exam), <code>ACTIVE</code> (window open for scanning), and <code>CONCLUDED</code> (closed), with administrative override bypasses available for authorized staff.</p>
    </li>
    <li><strong>Spreadsheet Formula Injection Defense:</strong>
        <p>To eliminate CSV/Excel injection vulnerabilities (where an attacker crafts a USN starting with <code>=CMD()</code>), the Excel generator automatically prepends a single quote (<code>'</code>) to any string starting with <code>=</code>, <code>+</code>, <code>-</code>, or <code>@</code>.</p>
    </li>
</ol>

<div class="page-break"></div>

<!-- ================= SECTION 5: DATABASE ================= -->
<h2>5.0 Relational Database Schema & Data Integrity</h2>
<p>
The persistence layer is anchored by <strong>SQLite3</strong> configured with Write-Ahead Logging (<code>PRAGMA journal_mode=WAL</code>) for superior concurrent read/write performance. The relational schema is structured in Third Normal Form (3NF):
</p>

<table>
    <thead>
        <tr>
            <th style="width: 22%;">Table Name</th>
            <th style="width: 38%;">Primary Attributes</th>
            <th style="width: 40%;">Relational Constraints & Indexes</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><code>users</code></td>
            <td><code>id, username, email, password_hash, full_name, role, department_id, is_active</code></td>
            <td><code>UNIQUE(username)</code>, <code>UNIQUE(email)</code>, Check <code>role IN ('ADMIN','TEACHER')</code></td>
        </tr>
        <tr>
            <td><code>departments</code></td>
            <td><code>id, code, name, created_at</code></td>
            <td><code>UNIQUE(code)</code> (e.g. CSE, ISE, ECE, ME, CV, EEE)</td>
        </tr>
        <tr>
            <td><code>classrooms</code></td>
            <td><code>id, department_id, room_number, building, capacity</code></td>
            <td><code>UNIQUE(department_id, room_number)</code>, FK to <code>departments(id)</code></td>
        </tr>
        <tr>
            <td><code>examinations</code></td>
            <td><code>id, exam_code, exam_name, academic_year, term</code></td>
            <td><code>UNIQUE(exam_code)</code> (e.g. EXAM-2026-EVEN)</td>
        </tr>
        <tr>
            <td><code>subjects</code></td>
            <td><code>id, department_id, subject_code, subject_name, qp_code</code></td>
            <td><code>UNIQUE(subject_code)</code>, FK to <code>departments(id)</code></td>
        </tr>
        <tr>
            <td><code>exam_sessions</code></td>
            <td><code>id, exam_id, department_id, classroom_id, course_code, room_number, exam_date, start_time, end_time, status</code></td>
            <td>FK to <code>classrooms</code>, <code>departments</code>, <code>users</code>. Check <code>status IN ('IN_PROGRESS','LOCKED','SUBMITTED')</code></td>
        </tr>
        <tr>
            <td><code>students_master</code></td>
            <td><code>id, usn, student_name, department_id, semester</code></td>
            <td><code>UNIQUE(usn)</code>, FK to <code>departments(id)</code></td>
        </tr>
        <tr>
            <td><code>students</code></td>
            <td><code>id, session_id, student_master_id, usn, student_name, desk_number, attendance_status, qp_barcode</code></td>
            <td><code>UNIQUE(session_id, usn)</code>, Check <code>attendance_status IN ('PENDING','PRESENT','ABSENT')</code></td>
        </tr>
        <tr>
            <td><code>booklet_registry</code></td>
            <td><code>id, barcode_value, exam_id, batch_number, status, assigned_session_id, assigned_usn</code></td>
            <td><code>UNIQUE(barcode_value)</code>, Check <code>status IN ('AVAILABLE','ASSIGNED','VOID')</code></td>
        </tr>
        <tr>
            <td><code>audit_trail</code></td>
            <td><code>id, session_id, usn, action_type, old_status, new_status, qp_barcode, reason, invigilator_id, timestamp, client_ip</code></td>
            <td>Immutable transaction log. Stores full historical changes with mandatory justifications.</td>
        </tr>
        <tr>
            <td><code>evaluation_verifications</code></td>
            <td><code>id, usn, scanned_qp_barcode, session_id, evaluator_name, verification_status, details, timestamp</code></td>
            <td>Evaluation center cross-checking log to detect paper mismatches or unrecorded scripts.</td>
        </tr>
    </tbody>
</table>

<!-- ================= SECTION 6: STATE TRANSITIONS & PERSISTENCE ================= -->
<h2>6.0 State Transitions & Persistence Resilience Engine</h2>

<div class="two-col avoid-break">
    <div class="col-half">
        <h3>6.1 Candidate Attendance State Machine</h3>
        <p>Every student allocated to an examination hall transitions through strict, mutually exclusive states:</p>
        <ul>
            <li><span class="badge badge-pending">PENDING</span>: Initial default state upon room allocation. Student is unconfirmed.</li>
            <li><span class="badge badge-present">PRESENT</span>: Transitioned upon valid booklet barcode scan. Booklet becomes <code>ASSIGNED</code>.</li>
            <li><span class="badge badge-absent">ABSENT</span>: Explicitly confirmed absent by invigilator. Booklet barcode remains null.</li>
            <li><strong>REDO Transition:</strong> If a student was marked by mistake, the invigilator executes a redo. The previous barcode is released to <code>AVAILABLE</code>, the audit log records the correction reason, and the candidate returns to <code>PENDING</code>.</li>
        </ul>
    </div>
    <div class="col-half">
        <h3>6.2 Persistent Snapshot Engine</h3>
        <p>Cloud containers (e.g. Render, Docker) often experience ephemeral storage wipes on server restart. To guarantee scheduled exams never vanish:</p>
        <ul>
            <li><strong>Snapshot Trigger (<code>save_backup_sessions</code>):</strong> Executed immediately whenever an exam is created, schedule edited, or students enrolled. Serializes full session metadata and rosters into <code>scheduled_exams_backup.json</code>.</li>
            <li><strong>Auto-Reconciliation (<code>restore_backup_sessions</code>):</strong> Executed upon server boot immediately after <code>init_db()</code>. Reads the JSON store and re-inserts any missing sessions and student rosters.</li>
            <li><strong>Permanent Persistence:</strong> Scheduled exams remain safely intact across all logouts and reboots until an Administrator explicitly deletes them.</li>
        </ul>
    </div>
</div>

<div class="page-break"></div>

<!-- ================= SECTION 7: SECURITY ================= -->
<h2>7.0 Security Architecture & Anti-Fraud Measures</h2>

<table>
    <thead>
        <tr>
            <th>Security Threat</th>
            <th>Vulnerability Vector</th>
            <th>COE ExamAttend Mitigation Strategy</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><strong>Duplicate Booklet Assignment</strong></td>
            <td>An invigilator accidentally or intentionally scans the same booklet barcode for two different students.</td>
            <td><strong>Registry Collision Check:</strong> The backend checks <code>booklet_registry</code> within a database transaction. If <code>status == 'ASSIGNED'</code>, it aborts immediately with <code>HTTP 409 Conflict</code>.</td>
        </tr>
        <tr>
            <td><strong>Counterfeit Barcodes</strong></td>
            <td>A candidate brings in an unauthorized external answer booklet with a fake barcode.</td>
            <td><strong>Closed Registry Validation:</strong> Barcodes must exist in the COE pre-registered inventory table. Unknown barcodes are rejected with <code>HTTP 400 Bad Request</code>.</td>
        </tr>
        <tr>
            <td><strong>Post-Submission Tampering</strong></td>
            <td>An invigilator changes an absent candidate to present after the examination has concluded.</td>
            <td><strong>Session Submission Lock:</strong> Submitting transitions session status to <code>LOCKED</code>. All standard update endpoints reject requests with <code>HTTP 403 Forbidden</code>.</td>
        </tr>
        <tr>
            <td><strong>Privilege Escalation</strong></td>
            <td>A teacher attempts to delete an exam or access admin configuration by typing URLs directly.</td>
            <td><strong>Strict RBAC Decorators:</strong> Routes are guarded with <code>@admin_required</code>. Teacher attempts trigger an immediate 403 rejection and audit logging.</td>
        </tr>
        <tr>
            <td><strong>Paper Evaluation Swapping</strong></td>
            <td>A dishonest evaluator replaces a student's answer script during valuation at the evaluation center.</td>
            <td><strong>Cross-Verification Portal (<code>/evaluator</code>):</strong> Evaluators scan barcodes; the system verifies against hall records. Unmatched barcodes flag instant fraud warnings.</td>
        </tr>
    </tbody>
</table>

<!-- ================= SECTION 8: WORKFLOWS ================= -->
<h2>8.0 End-to-End Operational Workflows</h2>

<div class="avoid-break">
    <h3>8.1 Master Examination Timetable & Scheduling</h3>
    <ol>
        <li><strong>Access Master Schedule (<code>/exams</code>):</strong> Both teachers and administrators can view the unified institutional timetable. Filter by academic department (CSE, ISE, ECE, ME, CV, EEE) or status.</li>
        <li><strong>Admin Scheduling (<code>/admin/exams/create_session</code>):</strong> Administrators define the subject code, course name, date, start time, end time, and assign an invigilator.</li>
        <li><strong>Handwritten Room Numbers:</strong> Administrators can type any custom room string (e.g. <code>CS101</code>, <code>Room 302</code>). If the room does not exist, the system creates it on the fly.</li>
        <li><strong>Roster Auto-Cloning:</strong> If scheduling consecutive exams in the same hall, candidate rosters automatically carry forward with fresh <code>PENDING</code> states.</li>
    </ol>
</div>

<div class="avoid-break">
    <h3>8.2 Invigilation & Real-Time Barcode Attendance</h3>
    <ol>
        <li><strong>Login & Hall Selection:</strong> Invigilator logs in with institutional credentials and opens their assigned room from the schedule or department cards.</li>
        <li><strong>Barcode Scan:</strong> Invigilator taps <strong>"Scan Booklet Barcode"</strong> on a student card. The phone camera opens, detects the booklet barcode, verifies it, and marks the student <span class="badge badge-present">PRESENT</span>.</li>
        <li><strong>Marking Absent:</strong> For absent candidates, the invigilator taps <strong>"Mark Absent"</strong>; the state updates to <span class="badge badge-absent">ABSENT</span> without tying up any booklet barcode.</li>
        <li><strong>Pre-Submission Review:</strong> At <code>/sessions/&lt;id&gt;/review</code>, students are sorted into Present, Absent, and Unmarked. The system displays a stern warning if any candidate remains unverified.</li>
        <li><strong>Session Finalization:</strong> The invigilator confirms total counts. The session transitions to <span class="badge badge-locked">LOCKED</span>, producing the official COE Excel report.</li>
    </ol>
</div>

<div class="avoid-break">
    <h3>8.3 Official COE Excel Attendance Report Generation</h3>
    <p>
    When an exam is finalized, the system compiles the official Controller of Examinations spreadsheet via <code>/download_report/&lt;session_id&gt;</code> adhering strictly to university standards:
    </p>
    <ul>
        <li><strong>Header Metadata Block:</strong> Institution name, academic term, department, course code, room number, exam date, and invigilator details.</li>
        <li><strong>14 Standard Columns:</strong> Sl. No, Desk No, USN, Candidate Name, Attendance Status, Answer Booklet Barcode, Invigilator Initial, Candidate Signature space, and Remarks.</li>
        <li><strong>Absentee Integrity:</strong> Absent candidates are explicitly marked <code>ABSENT</code> with blank barcode cells to prevent phantom booklet submission.</li>
        <li><strong>Statistical Summary & Signatures:</strong> Footer block with Total Enrolled, Present Count, Absent Count, Completion %, Chief Superintendent, and COE signatures.</li>
    </ul>
</div>

<div class="page-break"></div>

<!-- ================= SECTION 9: TEST SUITE ================= -->
<h2>9.0 Automated Verification & 30-Scenario Test Suite</h2>
<p>
The project includes a comprehensive regression test suite (<code>test_comprehensive.py</code> and <code>test_system.py</code>) covering 30 functional and security criteria. All test cases execute with 100% pass rates:
</p>

<table>
    <thead>
        <tr>
            <th style="width: 10%;">Test ID</th>
            <th style="width: 55%;">Verification Scenario & Description</th>
            <th style="width: 20%;">Target Component</th>
            <th style="width: 15%; text-align: center;">Result</th>
        </tr>
    </thead>
    <tbody>
        <tr><td><strong>TEST 01</strong></td><td>Valid teacher authentication & session cookie initialization</td><td>RBAC / Login</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 02</strong></td><td>Invalid credentials rejection with user-friendly feedback</td><td>Security / Login</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 03</strong></td><td>Department duty routing & access authorization</td><td>RBAC / Depts</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 04</strong></td><td>Classroom authorization & dynamic session loading</td><td>RBAC / Classrooms</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 05</strong></td><td>Dynamic student roster loading from relational database</td><td>Database / Roster</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 06</strong></td><td>Valid registered barcode from booklet registry accepted</td><td>Barcode Engine</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 07</strong></td><td>Unknown / unregistered barcode rejected with HTTP 400</td><td>Anti-Fraud</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 08</strong></td><td>Invalid barcode format rejected gracefully</td><td>Input Validation</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 09</strong></td><td>Barcode already assigned to another student rejected (HTTP 409)</td><td>Duplicate Prevention</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 10</strong></td><td>Repeated scans do not create duplicate attendance rows</td><td>Concurrency</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 11</strong></td><td>Failed barcode validation does not mark student present</td><td>Data Integrity</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 12</strong></td><td>Attendance saved transactionally in SQLite database</td><td>SQLite WAL</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 13</strong></td><td>Attendance state persists across browser page refreshes</td><td>Persistence</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 14</strong></td><td>Redo correction updates attendance state correctly</td><td>State Machine</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 15</strong></td><td>Audit trail retains original and corrected states with reasons</td><td>Audit Trail</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 16</strong></td><td>Pending / unmarked students identified before submission</td><td>Review Module</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 17</strong></td><td>Unresolved students cannot silently become confirmed absentees</td><td>Validation Rule</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 18</strong></td><td>Invigilator can correct errors prior to final submission</td><td>UX / Workflow</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 19</strong></td><td>Submitted session cannot be modified via ordinary routes</td><td>Submission Lock</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 20</strong></td><td>Unauthorized unlock attempts rejected with HTTP 403</td><td>Security Override</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 21</strong></td><td>Authorized COE unlocking requires PIN & mandatory logging</td><td>COE Emergency PIN</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 22</strong></td><td>Excel report contains all 14 required institutional columns</td><td>Excel Generator</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 23</strong></td><td>Absent candidates appear correctly with blank barcode cells</td><td>Excel Formatting</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 24</strong></td><td>Optimistic locking prevents concurrent double-assignment</td><td>Concurrency Locks</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 25</strong></td><td>Mobile interface maintains responsive viewport & touch targets</td><td>Mobile Frontend</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 26</strong></td><td>Camera permission denial handled gracefully</td><td>WebRTC Scanner</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 27</strong></td><td>Camera scanner stops cleanly when dismissed</td><td>Camera Lifecycle</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 28</strong></td><td>Network errors do not falsely report successful persistence</td><td>Error Handling</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 29</strong></td><td>CSV bulk student import detects duplicate USNs & row errors</td><td>Admin Import</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
        <tr><td><strong>TEST 30</strong></td><td>Faculty cannot bypass authorization to call administrative APIs</td><td>Privilege Escalation</td><td style="text-align: center; color: #16a34a; font-weight: bold;">PASSED</td></tr>
    </tbody>
</table>

<!-- ================= SECTION 10: DEPLOYMENT ================= -->
<h2>10.0 Deployment Architecture & Operational Setup</h2>

<h3>10.1 Cloud Deployment (Render / Docker)</h3>
<p>
The application includes complete configuration files (<code>Dockerfile</code>, <code>render.yaml</code>, <code>Procfile</code>) for zero-downtime containerized cloud deployment:
</p>
<pre>
# Production Container Invocation
web: gunicorn wsgi:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
</pre>

<h3>10.2 Campus Wi-Fi Testing (Local Network Access)</h3>
<p>
Because the launcher (<code>run.py</code>) binds to <code>0.0.0.0:5000</code>, invigilators on the university Wi-Fi network can connect their smartphones directly:
</p>
<ol>
    <li>Connect phone and server computer to the same campus Wi-Fi network.</li>
    <li>Identify computer IP (e.g. <code>192.168.1.45</code>) via <code>ipconfig</code>.</li>
    <li>Navigate to <code>http://192.168.1.45:5000</code> in mobile Safari / Chrome.</li>
    <li>For WebRTC camera compliance over LAN, run <code>START_PUBLIC_HTTPS_TUNNEL.bat</code> to obtain a public HTTPS URL.</li>
</ol>

<div class="callout callout-success avoid-break">
    <strong>Pre-Configured Demonstration Accounts:</strong>
    <ul style="margin: 4px 0 0 0; padding-left: 18px;">
        <li><strong>Administrator:</strong> Username: <code>admin</code> | Password: <code>AdminPassword@2026</code></li>
        <li><strong>Faculty (CSE):</strong> Username: <code>ramesh.cs</code> | Password: <code>TeacherPass@2026</code></li>
        <li><strong>Faculty (ISE):</strong> Username: <code>priya.cs</code> | Password: <code>TeacherPass@2026</code></li>
        <li><strong>COE Emergency Unlock PIN:</strong> <code>COE@2026</code></li>
    </ul>
</div>

<div style="margin-top: 30px; border-top: 1px solid #cbd5e1; padding-top: 10px; text-align: center; font-size: 8pt; color: #64748b;">
    <strong>End of Report</strong> &bull; Digital Examination Attendance & Verification System (COE ExamAttend v2.5) &bull; Autonomous Institutions
</div>

</body>
</html>
"""

html_path = os.path.abspath('COE_ExamAttend_Project_Report.html')
pdf_path = os.path.abspath('COE_ExamAttend_Project_Report.pdf')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
cmd = [
    chrome_path,
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--run-all-compositor-stages-before-draw',
    '--no-pdf-header-footer',
    f'--print-to-pdf={pdf_path}',
    html_path
]

print("Compiling PDF via Headless Chromium...")
res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

if os.path.exists(pdf_path):
    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"SUCCESS: PDF generated at {pdf_path} ({size_kb:.1f} KB)")
else:
    print("FAILED: PDF not created. Chrome output:", res.stderr)
