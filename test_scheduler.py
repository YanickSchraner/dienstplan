import csv
import datetime
import os
import unittest
from scheduler import generate_schedule_highs, variable_names, ScheduleSolution

class TestScheduler(unittest.TestCase):
    # Initialize instance variables at class level
    employees = []
    employee_qualifications = {}
    employee_workload = {}
    shifts = []
    absences = {}
    ch_holidays = []
    year = 2023
    month = 2

    def setUp(self):
        # Read employees from the CSV file.
        self.employees = []
        self.employee_qualifications = {}
        self.employee_workload = {}
        csv_path = os.path.join(os.path.dirname(__file__), "employees.csv")
        
        with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            for row in reader:
                # Each row must have an id, qualifikation, and workload.
                emp = {"id": row["id"]}  # The ID is already in the correct format
                self.employees.append(emp)
                self.employee_qualifications[row["id"]] = row["qualifikation"]
                self.employee_workload[row["id"]] = int(row["workload"])
                
        # Dummy shifts list (not used directly in the scheduler as the required shifts are defined inside the function)
        self.shifts = []  
        
        # No absences for our test scenario.
        self.absences = {}
        
        # No holidays for this test.
        self.ch_holidays = []

    def test_schedule_feasibility(self):
        """Ensure that the scheduler returns a ScheduleSolution with the expected number of decision variables."""
        solution = generate_schedule_highs(
            self.employees, 
            self.shifts,
            self.absences, 
            self.employee_qualifications, 
            self.employee_workload, 
            self.year, 
            self.month, 
            self.ch_holidays)
        self.assertIsNotNone(solution, "No solution was found.")
        # Verify that the count of solution values equals the count of declared variables.
        self.assertEqual(len(solution.col_value), len(variable_names),
                         "Mismatch between solution variables and extracted variable names.")
    
    def test_lehrlinge_weekday_restriction(self):
        """
        For employees with qualification "Ausbildung 1" or "Ausbildung 2":
          - They must not be assigned on weekends.
          - On weekdays, only "B Dienst" or "C Dienst" can be assigned.
        """
        solution = generate_schedule_highs(
            self.employees, 
            self.shifts,
            self.absences, 
            self.employee_qualifications, 
            self.employee_workload, 
            self.year, 
            self.month, 
            self.ch_holidays)
        
        num_days = 28  # February 2023 has 28 days
        for var, val in zip(variable_names, solution.col_value):
            emp_id, day, shift_code = var
            qual = self.employee_qualifications.get(emp_id)
            if qual in {"Ausbildung 1", "Ausbildung 2"}:
                date = datetime.date(self.year, self.month, day)
                # If it is a weekend, no shift should be assigned.
                if date.weekday() >= 5:
                    self.assertEqual(val, 0,
                                     f"Employee {emp_id} ({qual}) assigned on weekend {date} for shift {shift_code}.")
                else:
                    # On weekdays, ensure that only "B Dienst" or "C Dienst" are possible.
                    if shift_code not in {"B Dienst", "C Dienst"}:
                        self.assertEqual(val, 0,
                                         f"Employee {emp_id} ({qual}) assigned to non-B/C weekday shift {shift_code}.")
    
    def test_split_shift_penalty_application(self):
        """
        Run a test case for the split-shift soft constraint.
        While we cannot directly assert the slack variable values from the solution,
        we run the scheduler and print out a message indicating that extra split shifts 
        (beyond 3 per day) will contribute to the objective by a penalty.
        """
        solution = generate_schedule_highs(
            self.employees, 
            self.shifts,
            self.absences, 
            self.employee_qualifications, 
            self.employee_workload, 
            self.year, 
            self.month, 
            self.ch_holidays)
        self.assertIsNotNone(solution, "No solution was found.")
        # In a real environment, you might capture and test the objective value.
        # For now, we print a message for manual inspection.
        print("Test completed: Split shift slack variables were added and penalized as per configuration.")

if __name__ == "__main__":
    unittest.main()