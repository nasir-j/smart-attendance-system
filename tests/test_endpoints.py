import os
import sys
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app
from seed_data import populate_demo_data

class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        populate_demo_data()
        cls.client = app.test_client()
        app.config['TESTING'] = True

    def test_01_login_get(self):
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Smart Attendance', res.data)

    def test_02_login_post_and_dashboard(self):
        res = self.client.post('/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'System Dashboard', res.data)

    def test_03_students_list(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'
            sess['full_name'] = 'System Administrator'

        res = self.client.get('/admin/students')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MOHAMMAD AZEEM', res.data)
        self.assertIn(b'25CAMSA101', res.data)

    def test_04_sessions_list(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'
            sess['full_name'] = 'System Administrator'

        res = self.client.get('/sessions')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Attendance Sessions', res.data)

    def test_05_attendance_search(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'
            sess['full_name'] = 'System Administrator'

        res = self.client.get('/attendance/search?class_name=CAMSA')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'CAMSA', res.data)

    def test_06_attendance_reports(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'
            sess['full_name'] = 'System Administrator'

        res = self.client.get('/attendance/reports')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Attendance Reports', res.data)
        self.assertIn(b'25CAMSA101', res.data)

    def test_07_csv_exports(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'ADMIN'
            sess['full_name'] = 'System Administrator'

        res = self.client.get('/attendance/search?export=csv')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'text/csv; charset=utf-8')

        res_rep = self.client.get('/attendance/reports?export=csv')
        self.assertEqual(res_rep.status_code, 200)
        self.assertEqual(res_rep.headers.get('Content-Type'), 'text/csv; charset=utf-8')

if __name__ == '__main__':
    unittest.main()
