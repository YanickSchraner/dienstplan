from constraint import Problem, InSetConstraint, OptimizedBacktrackingSolver, MinConflictsSolver
import calendar
from datetime import date
import logging

# Configure logging (keep this at the top of the file)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_schedule(employees, shifts, absences, employee_qualifications, employee_workload, year, month, ch_holidays):
    logging.info(f"Generating schedule for {calendar.month_name[month]} {year}")
    problem = Problem(OptimizedBacktrackingSolver())

    # --- Variables ---
    num_days = calendar.monthrange(year, month)[1]
    days = [str(day) for day in range(1, num_days + 1)]
    days = days[:2] # Only consider first 2 days of the month for debugging
    variables = []
    for employee in employees:
        for day in days:
            day_str_key = f"{day.zfill(2)}.{month}.{year}" # Create key in 'DD.MM.YYYY' format for absence check
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0] # Extract day part
                    if absence_day == day:
                        is_absent = True
                        break # Employee is absent on this day, no variable needed

            if not is_absent: # Only create variable if NOT absent
                variable_name = (employee['id'], day)
                variables.append(variable_name)
                problem.addVariables([variable_name], [shift['code'] for shift in shifts] + [None])
    logging.info(f"Variables created: {variables}")


    # --- Constraints --- (All constraints remain the same, but with added logging)

    # 2. Employee Workload (Soft Constraint - now includes Büro Tage)
    logging.info("Adding Workload Constraints...")
    def workload_constraint(employee_id, *shifts):
        logging.debug(f"Workload constraint for employee {employee_id}")
        workload_cost = 0 # Initialize cost

        # Workload days deviation cost
        target_days = employee_workload.get(employee_id, 0)
        actual_days = sum(s is not None for s in shifts)
        deviation = abs(actual_days - target_days)
        workload_cost += deviation * 10  # Weight for workload deviation

        # Büro Tage Soft Constraint Cost
        if employee_qualifications.get(employee_id) == 'Leitung':
            büro_tage_target = 4
            büro_tage_actual = shifts.count("Bü Dienst")
            büro_tage_deviation = abs(büro_tage_actual - büro_tage_target)
            workload_cost += büro_tage_deviation * 5 # Weight for Büro Tage deviation - can be adjusted

        return workload_cost < 50 # Overall soft constraint limit (adjust as needed)


    for employee_id in employee_workload:
        employee_days_variables = [] # Collect variables only for non-absence days
        for day in days:
            day_str_key = f"{day.zfill(2)}.{month}.{year}" # Match absence data format
            is_absent = False
            if employee_id in absences:
                for absence_day_str, absence_type in absences[employee_id]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent:
                employee_days_variables.append((employee_id, str(day)))


        if employee_days_variables: # Only add workload constraint if employee has variables assigned
            logging.info(f"Adding workload constraint for employee {employee_id} with variables: {employee_days_variables}") # ADDED LOGGING
            problem.addConstraint(
                lambda *shifts, eid=employee_id: workload_constraint(eid, *shifts),
                employee_days_variables
            )
        else:
            logging.info(f"Employee {employee_id} has no variables (all days absent), skipping workload constraint.")
    logging.info("Workload Constraints Added.")

    # 3. Qualification per Shift TYPE
    early_shifts = ["B Dienst", "C Dienst", "BS Dienst", "C4 Dienst"]
    late_shifts = ["VS Dienst", "S Dienst"]

    logging.info("Adding Qualification Constraints...")
    for day in days:
        # Early Shifts
        variables_early_qual1 = []
        for employee in employees:
            day_str_key = f"{day.zfill(2)}.{month}.{year}"
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent:
                variables_early_qual1.append((employee['id'], day))


        if variables_early_qual1: # Only add constraint if there are variables for this day
            logging.info(f"Adding early qual constraint 1 for day {day} and variables: {variables_early_qual1}") # ADDED LOGGING
            def early_qual_constraint1(*shifts):
                logging.debug(f"Early qual constraint 1 for day {day}")
                return 1 <= sum(employee_qualifications.get(emp_id) in ("HF", "PH") for emp_id, shift in zip([e['id'] for e in employees], shifts) if shift in early_shifts) <= 2
            problem.addConstraint(
                early_qual_constraint1,
                variables_early_qual1
            )
        else:
            logging.info(f"No variables for early qual constraint 1 on day {day}, skipping.")


        variables_early_qual2 = []
        for employee in employees:
            day_str_key = f"{day.zfill(2)}.{month}.{year}"
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent:
                variables_early_qual2.append((employee['id'], day))

        if variables_early_qual2: # Only add constraint if there are variables for this day
            logging.info(f"Adding early qual constraint 2 for day {day} and variables: {variables_early_qual2}") # ADDED LOGGING
            def early_qual_constraint2(*shifts):
                logging.debug(f"Early qual constraint 2 for day {day}")
                return 4 <= sum(employee_qualifications.get(emp_id) in ("Leitung", "Ausbildung") for emp_id, shift in zip([e['id'] for e in employees], shifts) if shift in early_shifts) <= 6
            problem.addConstraint(
                early_qual_constraint2,
                variables_early_qual2
            )
        else:
             logging.info(f"No variables for early qual constraint 2 on day {day}, skipping.")


        # Late Shifts
        variables_late_qual1 = []
        for employee in employees:
            day_str_key = f"{day.zfill(2)}.{month}.{year}"
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent:
                variables_late_qual1.append((employee['id'], day))

        if variables_late_qual1: # Only add constraint if there are variables for this day
            logging.info(f"Adding late qual constraint 1 for day {day} and variables: {variables_late_qual1}") # ADDED LOGGING
            def late_qual_constraint1(*shifts):
                logging.debug(f"Late qual constraint 1 for day {day}")
                return 0 <= sum(employee_qualifications.get(emp_id) in ("HF", "PH") for emp_id, shift in zip([e['id'] for e in employees], shifts) if shift in late_shifts) <= 1 # Relaxed constraint
            problem.addConstraint(
                late_qual_constraint1,
                variables_late_qual1
            )
        else:
            logging.info(f"No variables for late qual constraint 1 on day {day}, skipping.")


        variables_late_qual2 = []
        for employee in employees:
            day_str_key = f"{day.zfill(2)}.{month}.{year}"
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent:
                variables_late_qual2.append((employee['id'], day))
        if variables_late_qual2: # Only add constraint if there are variables for this day
            logging.info(f"Adding late qual constraint 2 for day {day} and variables: {variables_late_qual2}") # ADDED LOGGING
            def late_qual_constraint2(*shifts):
                logging.debug(f"Late qual constraint 2 for day {day}")
                return 2 <= sum(employee_qualifications.get(emp_id) not in ("HF", "PH") for emp_id, shift in zip([e['id'] for e in employees], shifts) if shift in late_shifts) <= 3
            problem.addConstraint(
                late_qual_constraint2,
                variables_late_qual2
            )
        else:
            logging.info(f"No variables for late qual constraint 2 on day {day}, skipping.")
    logging.info("Qualification Constraints Added.")


    logging.info("Adding Lehrling Constraint...")
    for employee in employees:
        if employee['qualifikation'] == 'Ausbildung':
            # Collect Sunday and holiday dates for the ENTIRE MONTH
            sundays_and_holidays = []
            for day_val in range(1, num_days + 1): # Iterate through all days of the month
                date_obj = date(year, month, day_val)
                if date_obj.weekday() == 6 or date_obj in ch_holidays: # 6 = Sunday
                    sundays_and_holidays.append(str(day_val))

            # Get ALL variables for this employee for the ENTIRE MONTH (even if we are only solving for first 2 days for debugging)
            employee_month_variables = []
            for day_val in range(1, num_days + 1): # Iterate through all days of the month
                day = str(day_val)
                day_str_key = f"{day.zfill(2)}.{month}.{year}"
                is_absent = False
                if employee['id'] in absences:
                    for absence_day_str, absence_type in absences[employee['id']]:
                        absence_day = absence_day_str.split('.')[0]
                        if absence_day == day:
                            is_absent = True
                            break
                if not is_absent:
                    employee_month_variables.append((employee['id'], day)) # Use day as string


            if employee_month_variables: # Only add constraint if employee has variables in the month
                logging.info(f"Adding monthly lehrling constraint for employee {employee['id']} with variables: {employee_month_variables}")
                def monthly_lehrling_constraint(*shifts): # Renamed constraint function to be clearer
                    logging.debug(f"Monthly Lehrling constraint for employee {employee['id']}")
                    sunday_holiday_shifts = 0
                    for day_index, shift in enumerate(shifts): # Need index to get the day from employee_month_variables
                        if shift is not None: # Only count assigned shifts
                            variable_name = employee_month_variables[day_index] # Get variable name tuple
                            day_str = variable_name[1] # Extract day string from tuple
                            if day_str in sundays_and_holidays: # Check if the day is a Sunday or Holiday
                                sunday_holiday_shifts += 1
                    return sunday_holiday_shifts <= 1 # Check monthly limit
                problem.addConstraint(
                    monthly_lehrling_constraint,
                    employee_month_variables # Pass ALL variables for the month
                )
            else:
                logging.info(f"No variables for Lehrling {employee['id']} in the month, skipping monthly lehrling constraint.")
    logging.info("Lehrling Constraint Added.")

    # 6. Spät-Frühdienst Transition (Soft Constraint)
    logging.info("Adding Spaet-Fruehdienst Constraint...")
    def spaet_frueh_constraint(shift1, shift2):
        logging.debug(f"Spät-Früh constraint: Shift1 {shift1}, Shift2 {shift2}")
        if shift1 is None or shift2 is None:
            return True

        forbidden_transitions = {
            "S Dienst": ["B Dienst", "C4 Dienst"],
            "VS Dienst": ["B Dienst","BS Dienst"],
            "BS Dienst": ["B Dienst", "C Dienst", "C4 Dienst"],
            "C4 Dienst":["BS Dienst", "B Dienst"]
        }
        if shift1 in forbidden_transitions and shift2 in forbidden_transitions[shift1]:
            return False
        return True

    for employee in employees:
        employee_days_variables = [] # Collect variables only for non-absence days to create pairs
        for day_index in range(len(days)):
            day = days[day_index]
            day_str_key = f"{day.zfill(2)}.{month}.{year}"
            is_absent = False
            if employee['id'] in absences:
                for absence_day_str, absence_type in absences[employee['id']]:
                    absence_day = absence_day_str.split('.')[0]
                    if absence_day == day:
                        is_absent = True
                        break
            if not is_absent and day_index < len(days) - 1: # Ensure there is a next day to create a pair
                next_day = days[day_index + 1]
                day_str_key_next_day = f"{next_day.zfill(2)}.{month}.{year}"
                is_absent_next_day = False
                if employee['id'] in absences:
                    for absence_day_str, absence_type in absences[employee['id']]:
                        absence_day = absence_day_str.split('.')[0]
                        if absence_day == next_day:
                            is_absent_next_day = True
                            break
                if not is_absent_next_day: # Only add pair if both days are not absence days
                    variables_spaet_frueh = [(employee['id'], day), (employee['id'], next_day)]
                    logging.info(f"Adding Spaet-Fruehdienst constraint for variables: {variables_spaet_frueh}") # ADDED LOGGING
                    problem.addConstraint(
                        spaet_frueh_constraint,
                        variables_spaet_frueh
                    )
    logging.info("Spaet-Fruehdienst Constraint Added.")


    # --- Solve (Find ALL Solutions) ---
    solutions = problem.getSolutions()
    logging.info(f"Found {len(solutions)} solutions")
    return solutions

# --- Sample Data (for testing) ---
if __name__ == '__main__':
    # --- Simplified Sample Data (for debugging) ---
    employees_data = [
        {'id': 'ZE', 'qualifikation': 'Leitung'},
        {'id': 'DR', 'qualifikation': 'HF'},
        {'id': 'KL', 'qualifikation': 'Ausbildung'},
        {'id': 'AA', 'qualifikation': 'PH'},
        {'id': 'BB', 'qualifikation': 'PH'},
        {'id': 'CC', 'qualifikation': 'PH'},
        {'id': 'DD', 'qualifikation': 'PH'},
        {'id': 'EE', 'qualifikation': 'PH'},
        {'id': 'FF', 'qualifikation': 'PH'},
        {'id': 'GG', 'qualifikation': 'HF'},
        {'id': 'HH', 'qualifikation': 'HF'},
        {'id': 'II', 'qualifikation': 'HF'},
        {'id': 'JJ', 'qualifikation': 'HF'},
        {'id': 'KK', 'qualifikation': 'HF'},


    ]
    shifts_data = [
        {'code': 'B Dienst'},
        {'code': 'C Dienst'},
        {'code': 'VS Dienst'},
        {'code': 'S Dienst'},
        {'code': 'Bü Dienst'},
        {'code': '.w'}
    ]
    absences_data = {
        'ZE': [('2.2.2025', '.w')]
    }
    employee_qualifications_data = {
        'ZE': 'Leitung',
        'DR': 'HF',
        'KL': 'Ausbildung',
        'AA': 'PH',
        'BB': 'PH',
        'CC': 'PH',
        'DD': 'PH',
        'EE': 'PH',
        'FF': 'PH',
        'GG': 'HF',
        'HH': 'HF',
        'II': 'HF',
        'JJ': 'HF',
        'KK': 'HF'
    }
    employee_workload_data = {
        'ZE': 2,
        'DR': 2,
        'KL': 2,
        'AA': 2,
        'BB': 2,
        'CC': 2,
        'DD': 2,
        'EE': 2,
        'FF': 2,
        'GG': 2,
        'HH': 2,
        'II': 2,
        'JJ': 2,
        'KK': 2
    }
    ch_holidays_data = [] # No holidays for now
    year = 2025
    month = 2


    # Generate schedule
    solutions = generate_schedule(employees_data, shifts_data, absences_data, employee_qualifications_data, employee_workload_data, year, month, ch_holidays_data)

    if solutions:
        print("Solutions found:")
        for solution in solutions:
            print(solution)
    else:
        print("No solutions found.")