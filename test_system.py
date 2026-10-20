"""
End-to-End Test Suite for Digital Examination Attendance and Verification System.
Validates all 10 core requirements through the Flask test client.
"""
import os
import sys
import unittest
import json

# Setup test DB path before importing database
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_attendance.db')
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass

import database
database.DB_PATH = TEST_DB_PATH

from app import app
from database import init_db, seed_demo_data, get_db

class TestExamAttendanceSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        init_db()
        seed_demo_data()

    def test_01_student_attendance_recording(self):
        """Feature 1: Student Attendance Recording"""
        payload = {
            'session_id': 1,
            'usn': '1MS21CS001',
            'qp_barcode': 'QP-2026-CS801-A',
            'invigilator_id': 'INV-TEST',
            'invigilator_name': 'Test Invigilator'
        }
        res = self.client.post('/api/attendance/mark', json=payload)
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['student']['status'], 'PRESENT')

    def test_02_duplicate_attendance_prevention(self):
        """Feature 2: Duplicate Attendance Prevention"""
        payload = {
            'session_id': 1,
            'usn': '1MS21CS001',
            'qp_barcode': 'QP-2026-CS801-A'
        }
        # Attempt to scan 1MS21CS001 again
        res = self.client.post('/api/attendance/mark', json=payload)
        data = res.get_json()
        self.assertEqual(res.status_code, 409)
        self.assertFalse(data['success'])
        self.assertTrue(data['duplicate'])
        self.assertIn("DUPLICATE PREVENTED", data['message'])

    def test_03_redo_attendance_option_and_audit(self):
        """Feature 3: Redo Attendance Option & Feature 6: Audit Trail"""
        # Redo CS001 from PRESENT to ABSENT
        payload = {
            'session_id': 1,
            'usn': '1MS21CS001',
            'new_status': 'ABSENT',
            'reason': 'Student fell ill and left hall with approval'
        }
        res = self.client.post('/api/attendance/redo', json=payload)
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['student']['status'], 'ABSENT')

        # Verify audit trail contains REDO_CORRECTION
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_trail WHERE usn = '1MS21CS001' AND action_type = 'REDO_CORRECTION'")
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['reason'], 'Student fell ill and left hall with approval')

    def test_04_unmarked_student_warning(self):
        """Feature 7: Unmarked Student Warning before final submission"""
        res = self.client.post('/api/session/confirm_lock', json={'session_id': 1, 'force_submit': False})
        data = res.get_json()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(data['warning'], 'unmarked_students')
        self.assertGreater(data['pending_count'], 0)

    def test_05_final_confirmation_locking_and_excel(self):
        """Feature 4, 5, 8: Final Confirmation, Auto Excel Generation & Locking"""
        res = self.client.post('/api/session/confirm_lock', json={'session_id': 1, 'force_submit': True})
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('report_filename', data)
        self.assertTrue(data['report_filename'].endswith('.xlsx'))

        # Verify session is locked
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM exam_sessions WHERE id = 1")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, 'LOCKED')

        # Verify download endpoint works
        dl_res = self.client.get('/download_report/1')
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.content_type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_06_locked_session_prevents_edits(self):
        """Feature 8: Modifications blocked when session is locked"""
        payload = {
            'session_id': 1,
            'usn': '1MS21CS003',
            'qp_barcode': 'QP-2026-CS801-A'
        }
        res = self.client.post('/api/attendance/mark', json=payload)
        data = res.get_json()
        self.assertEqual(res.status_code, 403)
        self.assertTrue(data['locked'])

    def test_07_authorized_unlock_override(self):
        """Feature 8: Authorized unlock with COE PIN"""
        # Invalid PIN
        res = self.client.post('/api/session/unlock_override', json={'session_id': 1, 'auth_code': 'WRONG_PIN'})
        self.assertEqual(res.status_code, 403)

        # Valid PIN
        res = self.client.post('/api/session/unlock_override', json={
            'session_id': 1, 
            'auth_code': 'COE@2026', 
            'reason': 'Emergency unlock for verification'
        })
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['success'])

        # Verify session is unlocked
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM exam_sessions WHERE id = 1")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, 'IN_PROGRESS')

    def test_08_paper_evaluation_cross_verification(self):
        """Feature 10: Paper Evaluation Cross-Verification"""
        # Mark CS002 as Present
        mark_res = self.client.post('/api/attendance/mark', json={
            'session_id': 1,
            'usn': '1MS21CS002',
            'qp_barcode': 'QP-2026-CS801-A'
        })
        self.assertEqual(mark_res.status_code, 200)

        # Test valid evaluation match
        res_match = self.client.post('/api/evaluator/verify', json={
            'usn': '1MS21CS002',
            'scanned_qp_barcode': 'QP-2026-CS801-A'
        })
        data_match = res_match.get_json()
        self.assertEqual(res_match.status_code, 200)
        self.assertTrue(data_match['is_valid'])
        self.assertEqual(data_match['status'], 'VERIFIED_MATCH')

        # Test discrepancy: Barcode mismatch
        res_mismatch = self.client.post('/api/evaluator/verify', json={
            'usn': '1MS21CS002',
            'scanned_qp_barcode': 'TAMPERED-BARCODE-XYZ'
        })
        data_mismatch = res_mismatch.get_json()
        self.assertEqual(res_mismatch.status_code, 200)
        self.assertFalse(data_mismatch['is_valid'])
        self.assertEqual(data_mismatch['status'], 'DISCREPANCY_FLAGGED')

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

if __name__ == '__main__':
    unittest.main()
