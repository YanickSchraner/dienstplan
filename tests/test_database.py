import unittest
import sqlite3
from database import get_db_connection, get_employee_absences

class TestEmployeeAbsences(unittest.TestCase):
    def setUp(self):
        # Create a test database connection
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor()
        
        # Clear the employees table
        self.cursor.execute("DELETE FROM employees")
        
        # Insert test data
        test_data = [
            # Basic test case with single dates
            (1, "Test1", None, None, "21.2.", None),  # Only Wunschfrei
            
            # Multiple comma-separated dates
            (2, "Test2", "5.2., 12.2., 19.2.", None, None, None),  # Only SL
            
            # Date ranges in Fe
            (3, "Test3", None, "15.2.-23.2.", None, None),  # Fe with range same month
            
            # Date range across months
            (4, "Test4", None, "28.2.-2.3.", None, None),  # Fe across months
            
            # Multiple types of absences
            (5, "Test5", "5.2.", "15.2.-17.2.", "21.2.", "8.2.-16.2."),  # All types
            
            # Invalid date formats (should be handled gracefully)
            (6, "Test6", None, "invalid-date", None, None),  # Invalid Fe format
            
            # Empty values
            (7, "Test7", "", "", "", ""),  # All empty
        ]
        
        self.cursor.executemany(
            "INSERT INTO employees (id, name, SL, Fe, w, UW) VALUES (?, ?, ?, ?, ?, ?)",
            test_data
        )
        self.conn.commit()

    def test_single_wunschfrei(self):
        absences = get_employee_absences()
        self.assertIn(1, absences)
        self.assertEqual(absences[1], [("21.2.", "w")])

    def test_multiple_sl_dates(self):
        absences = get_employee_absences()
        expected = [
            ("5.2.", "SL"),
            ("12.2.", "SL"),
            ("19.2.", "SL")
        ]
        self.assertEqual(sorted(absences[2]), sorted(expected))

    def test_ferien_range_same_month(self):
        absences = get_employee_absences()
        expected = [
            (f"{day}.2.", "Fe") for day in range(15, 24)  # 15.2. to 23.2.
        ]
        self.assertEqual(sorted(absences[3]), sorted(expected))

    def test_ferien_range_across_months(self):
        absences = get_employee_absences()
        expected = (
            [(f"{day}.2.", "Fe") for day in range(28, 32)] +  # 28.2. to 31.2.
            [(f"{day}.3.", "Fe") for day in range(1, 3)]      # 1.3. to 2.3.
        )
        self.assertEqual(sorted(absences[4]), sorted(expected))

    def test_multiple_absence_types(self):
        absences = get_employee_absences()
        expected = (
            [("5.2.", "SL")] +  # SL
            [(f"{day}.2.", "Fe") for day in range(15, 18)] +  # Fe
            [("21.2.", "w")] +  # Wunschfrei
            [(f"{day}.2.", "uw") for day in range(8, 17)]  # UW
        )
        self.assertEqual(sorted(absences[5]), sorted(expected))

    def test_invalid_date_format(self):
        absences = get_employee_absences()
        self.assertEqual(absences[6], [])  # Should return empty list for invalid dates

    def test_empty_values(self):
        absences = get_employee_absences()
        self.assertEqual(absences[7], [])  # Should return empty list for empty values

    def tearDown(self):
        self.conn.close()

if __name__ == '__main__':
    unittest.main() 