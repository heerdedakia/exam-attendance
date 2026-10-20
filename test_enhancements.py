import os
import sys
import unittest
import json
import sqlite3

TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_enhancements.db')
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass

import database
database.DB_PATH = TEST_DB_PATH

from app import app
from database import init_db, get_db

class TestEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        cls.client = app.test_client()
        init_db(TEST_DB_PATH)

    def test_01_teachername_login(self):
        """Test login with username 'teachername' without underscores"""
        res = self.client.post('/login', data={'username': 'teachername', 'password': 'TeacherPass@2026'}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('username'), 'teachername')
            self.assertEqual(sess.get('role'), 'TEACHER')
        self.client.get('/logout')

    def test_02_password_setup_self_service(self):
        """Test self-service password setup via /set_password"""
        res = self.client.post('/set_password', data={
            'username_or_email': 'teachername',
            'new_password': 'MyNewSecurePassword@123',
            'confirm_password': 'MyNewSecurePassword@123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"has been updated successfully", res.data)

        # Verify login works with new password
        login_res = self.client.post('/login', data={'username': 'teachername', 'password': 'MyNewSecurePassword@123'}, follow_redirects=False)
        self.assertEqual(login_res.status_code, 302)
        self.client.get('/logout')

    def test_03_classroom_create_and_increase_capacity(self):
        """Test creating a classroom and increasing capacity"""
        # Login as admin
        self.client.post('/login', data={'username': 'admin', 'password': 'AdminPassword@2026'})

        # Create classroom
        res_create = self.client.post('/admin/classrooms/create', data={
            'department_id': 1,
            'room_number': 'Hall 901',
            'building': 'Innovation Block',
            'capacity': 50
        }, follow_redirects=True)
        self.assertEqual(res_create.status_code, 200)

        conn = get_db(TEST_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, capacity FROM classrooms WHERE room_number = 'Hall 901'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        room_id = row['id']
        self.assertEqual(row['capacity'], 50)

        # Edit capacity to 120
        res_edit = self.client.post(f'/admin/classrooms/{room_id}/edit', data={
            'room_number': 'Hall 901',
            'building': 'Innovation Block',
            'capacity': 120
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        c.execute("SELECT capacity FROM classrooms WHERE id = ?", (room_id,))
        self.assertEqual(c.fetchone()['capacity'], 120)
        conn.close()
        self.client.get('/logout')

    def test_04_add_student_single_and_bulk(self):
        """Test individual student add and quick bulk paste add"""
        # Login as teacher
        self.client.post('/login', data={'username': 'teacherramesh', 'password': 'TeacherPass@2026'})

        # Single add to session 1
        res_add = self.client.post('/api/session/add_student', json={
            'session_id': 1,
            'usn': '1MS21CS999',
            'student_name': 'Test Candidate Special'
        })
        self.assertEqual(res_add.status_code, 200)
        data = res_add.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['student']['usn'], '1MS21CS999')

        # Bulk paste add to session 1
        raw_text = "1MS21CS981, Bulk Student One\n1MS21CS982, Bulk Student Two\n1MS21CS983, Bulk Student Three"
        res_bulk = self.client.post('/api/session/bulk_add_students', json={
            'session_id': 1,
            'raw_text': raw_text
        })
        self.assertEqual(res_bulk.status_code, 200)
        bulk_data = res_bulk.get_json()
        self.assertTrue(bulk_data['success'])
        self.assertEqual(bulk_data['added_count'], 3)

        # Verify students exist in DB
        conn = get_db(TEST_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM students WHERE session_id = 1 AND usn IN ('1MS21CS999', '1MS21CS981', '1MS21CS982', '1MS21CS983')")
        self.assertEqual(c.fetchone()[0], 4)
        conn.close()
        self.client.get('/logout')

if __name__ == '__main__':
    unittest.main()
