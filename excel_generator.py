"""
Excel Attendance Sheet Generator for Controller of Examinations (COE).
Generates an official, publication-quality, styled .xlsx report using openpyxl.
Includes formula injection prevention, comprehensive summary statistics,
and detailed attendance data compliant with institutional examination standards.
"""
import os
import re
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

def sanitize_excel_cell(val):
    """
    Prevents spreadsheet formula injection by prepending a single quote
    if an untrusted text value begins with =, +, -, @, or tab/return.
    """
    if val is None:
        return ""
    val_str = str(val)
    if val_str and val_str[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + val_str
    return val_str

def generate_coe_attendance_excel(session_data, students_list, output_path=None):
    """
    session_data: dict with keys:
        - course_code, course_name, exam_date, exam_session, room_number, qp_code,
          invigilator_name, invigilator_id, status, locked_at, department_name, exam_name
    students_list: list of dicts with:
        - usn, student_name, desk_number, attendance_status, qp_barcode, marked_at
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "COE Attendance Sheet"
    ws.views.sheetView[0].showGridLines = True

    # Color Palette
    NAVY_BLUE = "1E3A8A"
    LIGHT_BLUE = "DBEAFE"
    EMERALD_GREEN = "059669"
    LIGHT_GREEN = "D1FAE5"
    CRIMSON = "DC2626"
    LIGHT_RED = "FEE2E2"
    AMBER = "D97706"
    LIGHT_AMBER = "FEF3C7"
    GRAY_HEADER = "334155"
    BORDER_COLOR = "CBD5E1"

    thin_border = Border(
        left=Side(style='thin', color=BORDER_COLOR),
        right=Side(style='thin', color=BORDER_COLOR),
        top=Side(style='thin', color=BORDER_COLOR),
        bottom=Side(style='thin', color=BORDER_COLOR)
    )

    # Row 1: Title Header (Col A to N = 14 columns)
    ws.merge_cells("A1:N1")
    title_cell = ws["A1"]
    title_cell.value = "CONTROLLER OF EXAMINATIONS (COE) - OFFICIAL ATTENDANCE STATEMENT"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color=NAVY_BLUE, end_color=NAVY_BLUE, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    # Row 2: Subtitle
    ws.merge_cells("A2:N2")
    sub_cell = ws["A2"]
    sub_cell.value = "DIGITAL EXAMINATION ATTENDANCE & BOOKLET BARCODE VERIFICATION RECORD"
    sub_cell.font = Font(name="Calibri", size=11, bold=True, color="1E3A8A")
    sub_cell.fill = PatternFill(start_color=LIGHT_BLUE, end_color=LIGHT_BLUE, fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 24

    # Exam Metadata Section (Rows 4 to 7)
    dept_name = session_data.get('department_name') or 'Engineering'
    exam_title = session_data.get('exam_name') or 'Semester End Examination'
    submission_stat = "SUBMITTED / LOCKED" if session_data.get('status') == 'LOCKED' else (session_data.get('status') or 'IN_PROGRESS')

    meta_keys = [
        ("Examination:", sanitize_excel_cell(exam_title), "Exam Date:", sanitize_excel_cell(session_data['exam_date'])),
        ("Department:", sanitize_excel_cell(dept_name), "Exam Session:", sanitize_excel_cell(session_data['exam_session'])),
        ("Subject Code & Name:", f"{sanitize_excel_cell(session_data['course_code'])} - {sanitize_excel_cell(session_data['course_name'])}", "Classroom / Hall:", sanitize_excel_cell(session_data['room_number'])),
        ("Responsible Invigilator:", f"{sanitize_excel_cell(session_data['invigilator_name'])} ({sanitize_excel_cell(session_data['invigilator_id'])})", "Submission Timestamp:", sanitize_excel_cell(session_data.get('locked_at') or 'Draft / In Progress'))
    ]

    current_row = 4
    for label1, val1, label2, val2 in meta_keys:
        ws.cell(row=current_row, column=1, value=label1).font = Font(name="Calibri", bold=True, size=10, color="334155")
        ws.cell(row=current_row, column=1).alignment = Alignment(vertical="center")

        ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=7)
        v1_cell = ws.cell(row=current_row, column=2, value=val1)
        v1_cell.font = Font(name="Calibri", bold=(label1 in ("Examination:", "Subject Code & Name:")), size=10)
        v1_cell.alignment = Alignment(vertical="center")

        ws.cell(row=current_row, column=8, value=label2).font = Font(name="Calibri", bold=True, size=10, color="334155")
        ws.cell(row=current_row, column=8).alignment = Alignment(vertical="center")

        ws.merge_cells(start_row=current_row, start_column=9, end_row=current_row, end_column=14)
        v2_cell = ws.cell(row=current_row, column=9, value=val2)
        v2_cell.font = Font(name="Calibri", bold=True, size=10)
        v2_cell.alignment = Alignment(vertical="center")

        ws.row_dimensions[current_row].height = 20
        current_row += 1

    # Row 9: Statistical Summary Bar
    total_count = len(students_list)
    present_count = sum(1 for s in students_list if s['attendance_status'] == 'PRESENT')
    absent_count = sum(1 for s in students_list if s['attendance_status'] == 'ABSENT')
    pending_count = sum(1 for s in students_list if s['attendance_status'] == 'PENDING')
    pct = round((present_count / total_count * 100), 1) if total_count > 0 else 0.0

    current_row = 9
    ws.row_dimensions[current_row].height = 26

    # Total Box
    ws.merge_cells(f"A{current_row}:C{current_row}")
    cell_tot = ws[f"A{current_row}"]
    cell_tot.value = f"Total Assigned: {total_count}"
    cell_tot.font = Font(bold=True, size=10, color="1E293B")
    cell_tot.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    cell_tot.alignment = Alignment(horizontal="center", vertical="center")

    # Present Box
    ws.merge_cells(f"D{current_row}:F{current_row}")
    cell_pres = ws[f"D{current_row}"]
    cell_pres.value = f"Total Present: {present_count}"
    cell_pres.font = Font(bold=True, size=10, color="065F46")
    cell_pres.fill = PatternFill(start_color=LIGHT_GREEN, end_color=LIGHT_GREEN, fill_type="solid")
    cell_pres.alignment = Alignment(horizontal="center", vertical="center")

    # Absent Box
    ws.merge_cells(f"G{current_row}:I{current_row}")
    cell_abs = ws[f"G{current_row}"]
    cell_abs.value = f"Total Absent: {absent_count}"
    cell_abs.font = Font(bold=True, size=10, color="991B1B")
    cell_abs.fill = PatternFill(start_color=LIGHT_RED, end_color=LIGHT_RED, fill_type="solid")
    cell_abs.alignment = Alignment(horizontal="center", vertical="center")

    # Pending Box
    ws.merge_cells(f"J{current_row}:L{current_row}")
    cell_pend = ws[f"J{current_row}"]
    cell_pend.value = f"Total Pending: {pending_count}"
    cell_pend.font = Font(bold=True, size=10, color="92400E")
    cell_pend.fill = PatternFill(start_color=LIGHT_AMBER, end_color=LIGHT_AMBER, fill_type="solid")
    cell_pend.alignment = Alignment(horizontal="center", vertical="center")

    # Percentage Box
    ws.merge_cells(f"M{current_row}:N{current_row}")
    cell_pct = ws[f"M{current_row}"]
    cell_pct.value = f"Attendance Rate: {pct}%"
    cell_pct.font = Font(bold=True, size=10, color="1E3A8A")
    cell_pct.fill = PatternFill(start_color=LIGHT_BLUE, end_color=LIGHT_BLUE, fill_type="solid")
    cell_pct.alignment = Alignment(horizontal="center", vertical="center")

    # Row 11: Table Headers (Required Columns)
    headers = [
        "Serial No.",
        "Student USN",
        "Student Name",
        "Department",
        "Classroom",
        "Examination Code",
        "Subject",
        "Exam Date",
        "Exam Session",
        "Booklet Barcode",
        "Attendance Status",
        "Scan Timestamp",
        "Invigilator ID",
        "Submission Status"
    ]
    table_header_row = 11
    ws.row_dimensions[table_header_row].height = 28

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=table_header_row, column=col_idx, value=header)
        cell.font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill(start_color=GRAY_HEADER, end_color=GRAY_HEADER, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    # Table Rows
    data_start_row = 12
    row_num = data_start_row
    for idx, s in enumerate(students_list, start=1):
        ws.row_dimensions[row_num].height = 22
        status = s['attendance_status']

        # Safe values with formula injection protection
        usn_val = sanitize_excel_cell(s['usn'])
        name_val = sanitize_excel_cell(s['student_name'])
        dept_val = sanitize_excel_cell(dept_name)
        room_val = sanitize_excel_cell(session_data['room_number'])
        exam_code_val = sanitize_excel_cell(session_data.get('exam_code') or exam_title)
        subj_val = sanitize_excel_cell(f"{session_data['course_code']} - {session_data['course_name']}")
        date_val = sanitize_excel_cell(session_data['exam_date'])
        session_val = sanitize_excel_cell(session_data['exam_session'])

        # For absent students: booklet barcode and scan timestamp MUST BE EMPTY
        if status == 'ABSENT':
            barcode_val = ""
            time_val = ""
        else:
            barcode_val = sanitize_excel_cell(s.get('qp_barcode') or '')
            time_val = sanitize_excel_cell(s.get('marked_at') or '')

        invigilator_val = sanitize_excel_cell(session_data['invigilator_id'])
        sub_status_val = sanitize_excel_cell(submission_stat)

        row_data = [
            idx,
            usn_val,
            name_val,
            dept_val,
            room_val,
            exam_code_val,
            subj_val,
            date_val,
            session_val,
            barcode_val,
            status,
            time_val,
            invigilator_val,
            sub_status_val
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border

            # Specific alignments
            if col_idx in (1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            # Status formatting
            if col_idx == 11:
                if status == 'PRESENT':
                    cell.font = Font(name="Calibri", size=10, bold=True, color="065F46")
                    cell.fill = PatternFill(start_color=LIGHT_GREEN, end_color=LIGHT_GREEN, fill_type="solid")
                elif status == 'ABSENT':
                    cell.font = Font(name="Calibri", size=10, bold=True, color="991B1B")
                    cell.fill = PatternFill(start_color=LIGHT_RED, end_color=LIGHT_RED, fill_type="solid")
                else:
                    cell.font = Font(name="Calibri", size=10, bold=True, color="92400E")
                    cell.fill = PatternFill(start_color=LIGHT_AMBER, end_color=LIGHT_AMBER, fill_type="solid")

        row_num += 1

    # Certification and Signatures Section
    cert_row = row_num + 2
    ws.merge_cells(f"A{cert_row}:N{cert_row}")
    cert_cell = ws[f"A{cert_row}"]
    cert_cell.value = (
        f"CERTIFICATION STATEMENT: I hereby certify that the attendance record for classroom "
        f"{session_data['room_number']} in subject {session_data['course_code']} has been verified "
        f"via digital answer-booklet barcode scanning in accordance with institutional examination rules. "
        f"Total Present: {present_count}, Total Absent: {absent_count}, Pending: {pending_count}."
    )
    cert_cell.font = Font(name="Calibri", italic=True, size=10, color="1E293B")
    cert_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[cert_row].height = 28

    sign_row = cert_row + 3
    ws.cell(row=sign_row, column=2, value="____________________________").font = Font(bold=True)
    ws.cell(row=sign_row, column=7, value="____________________________").font = Font(bold=True)
    ws.cell(row=sign_row, column=12, value="____________________________").font = Font(bold=True)

    sign_title_row = sign_row + 1
    ws.cell(row=sign_title_row, column=2, value="Invigilator Signature").font = Font(bold=True, size=10)
    ws.cell(row=sign_title_row, column=7, value="Chief Superintendent").font = Font(bold=True, size=10)
    ws.cell(row=sign_title_row, column=12, value="COE Verification Seal").font = Font(bold=True, size=10)

    # Auto-adjust column widths
    col_widths = {
        'A': 10,  # Serial No
        'B': 18,  # Student USN
        'C': 26,  # Student Name
        'D': 24,  # Department
        'E': 18,  # Classroom
        'F': 20,  # Exam Code
        'G': 32,  # Subject
        'H': 14,  # Date
        'I': 22,  # Session
        'J': 20,  # Booklet Barcode
        'K': 18,  # Attendance Status
        'L': 22,  # Scan Timestamp
        'M': 16,  # Invigilator ID
        'N': 20   # Submission Status
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width

    # Sanitize filename components: Attendance_{Classroom}_{Date}_{Session}.xlsx
    clean_room = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_data['room_number']).strip('_')
    clean_date = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_data['exam_date']).strip('_')
    clean_session = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_data['exam_session'].split(' ')[0]).strip('_')

    if output_path is None:
        reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generated_reports')
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"Attendance_{clean_room}_{clean_date}_{clean_session}.xlsx"
        output_path = os.path.join(reports_dir, filename)

    wb.save(output_path)
    return output_path
