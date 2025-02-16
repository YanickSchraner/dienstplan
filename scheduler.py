import calendar
from ortools.linear_solver import pywraplp
import datetime

# Global variable used by app.py to extract the solution.
variable_names = []

class ScheduleSolution:
    def __init__(self, col_value):
        self.col_value = col_value

def generate_schedule_highs(employees, shifts, absences, employee_qualifications, employee_workload, year, month, ch_holidays):
    """
    A schedule generator using OR-Tools that enforces shift qualification constraints
    and various soft constraints with different penalties.

    The requirements modeled are:
      - Frühschicht:
          * "B Dienst": 3 assignments per day where exactly 1 employee has a fachliche Qualifikation
            ("HF" or "Leitung") and exactly 2 employees are non‑fachlich.
          * "C Dienst": 2 assignments per day – only non‑fach employees.
      - Spätschicht:
          * "S Dienst": 2 assignments per day with exactly 1 fach and 1 non‑fach.
          * "VS Dienst": 1 assignment per day (no qualification restriction).

    For simplicity, this basic model creates binary decision variables x[(e_id, d, shift_code)]
    for every employee for every day of the month and for each of the four required shift codes.
    It also ensures that an employee works at most one shift per day.
    
    NOTE: Absences, workload, and holidays are ignored in this basic implementation.

    Args:
        employees: List of employee dictionaries (id, qualifikation).
        shifts: List of shift dictionaries (code).
        absences: Dictionary of employee absences (employee_id: [(date_str, type)]).
        employee_qualifications: Dictionary of employee qualifications (employee_id: qualifikation).
        employee_workload: Dictionary of employee target workloads (employee_id: target_days).
        year: Year for the schedule.
        month: Month for the schedule.
        ch_holidays: List of holidays (as datetime.date objects).
    """
    global variable_names
    variable_names.clear()

    # Create the solver. Using CBC since it supports mixed-integer programming.
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    if not solver:
        print("Solver not created.")
        return None

    # ------------------------------------------
    # Penalty Definitions
    # ------------------------------------------
    # Qualification Requirements (Highest Priority)
    FACH_PENALTY = 5000          # Penalty for not meeting Fachkraft (HF/Leitung) requirements
    EARLY_FACH_PENALTY = 5000    # Penalty for not having a Fachkraft in early shifts
    LATE_HF_PENALTY = 5000       # Penalty for not having an HF in late shifts
    
    # Coverage Requirements (High Priority)
    EARLY_COVERAGE_PENALTY = 4000  # Penalty for not meeting minimum early shift coverage (5 employees)
    LATE_COVERAGE_PENALTY = 4000   # Penalty for not meeting minimum late shift coverage (3 employees)
    
    # Shift Requirements (Medium-High Priority)
    NONFACH_PENALTY = 3000       # Penalty for not meeting non-Fachkraft requirements
    B_DIENST_PENALTY = 3000      # Penalty for not meeting B Dienst minimum requirements (2 employees)
    
    # Workload Violations (Medium Priority)
    EXCESSIVE_WORKDAY_PENALTY = 2000  # Penalty for working any days over target
    
    # Shift Pattern Violations (Medium-Low Priority)
    CONSECUTIVE_SHIFT_PENALTY = 1000  # Penalty for violating consecutive shift rules (5 days max)
    
    # Target Workday Deviations (Low Priority)
    WORKDAY_DEVIATION_PENALTY = 100   # Penalty for deviating from target workdays (under only)
    
    # Shift Preference Penalties (Low Priority)
    EXTRA_FACH_LATE_PENALTY = 50  # Penalty for having more than one fachpersonal in late shifts
    
    # Regular Assignment Costs (Shift Preferences)
    EARLY_SHIFT_COST = 1         # Base cost for early shifts (B Dienst, C Dienst)
    LATE_SHIFT_COST = 3          # Higher cost for late shifts (S Dienst, VS Dienst) to prefer early shifts
    SPLIT_SHIFT_COST = 5         # Highest cost for split shifts (BS Dienst, C4 Dienst)
    
    # ------------------------------------------
    # Minimum Requirements
    # ------------------------------------------
    # Early Shift Requirements
    MIN_EARLY_TOTAL_WEEKDAY = 5    # Minimum total staff in early shifts on weekdays
    MIN_EARLY_TOTAL_WEEKEND = 5    # Minimum total staff in early shifts on weekends
    MIN_EARLY_FACH = 1           # Minimum Fachkraft required in early shifts
    
    # Late Shift Requirements
    MIN_LATE_TOTAL = 3           # Minimum total staff in late shifts
    MIN_LATE_HF = 1              # Minimum HF required in late shifts
    
    # Individual Shift Requirements
    MIN_B_DIENST = 2             # Minimum staff in B Dienst
    MAX_SPLIT_SHIFTS = 3         # Maximum split shifts per day
    
    # Workload Requirements
    MAX_CONSECUTIVE_DAYS = 5     # Maximum consecutive working days
    MIN_REST_AFTER_MAX = 2       # Minimum rest days after max consecutive days
    MAX_WEEKENDS = 2             # Maximum weekends per month per employee
    MAX_WEEKENDS_AUSB2 = 1       # Maximum weekends per month for Ausbildung 2
    
    # Büro Requirements
    BURO_DAYS_PER_MONTH = 4      # Required Büro days per month for Leitung
    
    # ------------------------------------------
    # Initialize Problem Variables
    # ------------------------------------------
    num_days = calendar.monthrange(year, month)[1]
    
    # Define the required shifts and their counts along with qualification restrictions.
    # For each shift code, we specify:
    #   - "total": total number of assignments per day.
    #   - "fach": number of employees required with fach (qualified) for that shift.
    #   - "nonfach": number of employees required from non‑fach group.
    required_shifts = {
        "B Dienst": {"total": 3, "fach": 1, "nonfach": 2},  # 1 fach + 2 non-fach
        "C Dienst": {"total": 1, "fach": 0, "nonfach": 1},  # 1 non-fach
        "S Dienst": {"total": 2, "fach": 1, "nonfach": 1},  # 1 fach + 1 non-fach
        "VS Dienst": {"total": 1},  # No qualification restrictions
        "BS Dienst": {"total": 0, "optional": True},  # Split shift (optional)
        "C4 Dienst": {"total": 0, "optional": True}   # Split shift (optional)
    }
    
    # Define which qualifications count as fach (qualified).
    fach_qual = {"HF", "Leitung"}

    # Create binary decision variables for each employee/day/shift.
    x = {}
    
    # Helper function to check if an employee is absent on a given day
    def employee_is_absent(e_id, d, month, absences):
         if e_id not in absences:
             return False
         for record in absences[e_id]:
             # record[0] is a date string in the format "DD.MM." (e.g. "7.2.")
             parts = record[0].split('.')
             if len(parts) >= 2:
                 try:
                     absence_day = int(parts[0])
                     absence_month = int(parts[1])
                     if absence_day == d and absence_month == month:
                         return True
                 except ValueError:
                     continue
         return False
    
    # Regular shift variables
    for d in range(1, num_days + 1):
        for shift_code in required_shifts.keys():
            for emp in employees:
                e_id = emp["id"]
                var = solver.BoolVar(f"{e_id}_{d}_{shift_code}")
                x[(e_id, d, shift_code)] = var
                variable_names.append((e_id, d, shift_code))
    
    # Bü Dienst variables for Leitung employees
    y = {}
    for d in range(1, num_days + 1):
        current_date = datetime.date(year, month, d)
        for emp in employees:
            e_id = emp["id"]
            var_y = solver.BoolVar(f"{e_id}_{d}_Bü Dienst")
            y[(e_id, d)] = var_y
            # If the employee is Leitung, add to variable_names
            if employee_qualifications.get(e_id) == "Leitung":
                variable_names.append((e_id, d, "Bü Dienst"))
            # If the day is weekend, the employee is not "Leitung",
            # or the employee is absent on that day, force Bü Dienst to 0.
            if current_date.weekday() >= 5 or employee_qualifications.get(e_id) != "Leitung" \
               or employee_is_absent(e_id, d, month, absences):
                solver.Add(var_y == 0)
    
    # Constraint: Each employee can work at most one shift per day.
    for d in range(1, num_days + 1):
        for emp in employees:
            e_id = emp["id"]
            # For Leitung employees, include Bü Dienst in the one-shift-per-day constraint
            if employee_qualifications.get(e_id) == "Leitung":
                solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) + y[(e_id, d)] <= 1)
            else:
                solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) <= 1)
    
    # ------------------------------------------
    # Availability constraints: an employee who is absent on a day
    # cannot be assigned any shift.
    for d in range(1, num_days + 1):
         for emp in employees:
             e_id = emp["id"]
             if employee_is_absent(e_id, d, month, absences):
                 solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)

    # ------------------------------------------
    # Additional constraints for Leitung employees.
    # ------------------------------------------
    # For Leitungs employees:
    for emp in employees:
        e_id = emp["id"]
        if employee_qualifications.get(e_id) == "Leitung":
            # 1. Only work on weekdays
            for d in range(1, num_days + 1):
                current_date = datetime.date(year, month, d)
                if current_date.weekday() >= 5:  # Weekend
                    solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)
                else:  # Weekday
                    # 2. Only B Dienst or Bü Dienst allowed (and not both on the same day)
                    for shift_code in required_shifts.keys():
                        if shift_code != "B Dienst":
                            solver.Add(x[(e_id, d, shift_code)] == 0)
                    solver.Add(x[(e_id, d, "B Dienst")] + y[(e_id, d)] <= 1)
            
            # 3. Must have exactly 4 Büro days per month
            solver.Add(sum(y[(e_id, d)] for d in range(1, num_days + 1)
                         if datetime.date(year, month, d).weekday() < 5) == BURO_DAYS_PER_MONTH)

    # For each day and for each non-optional shift code, set individual coverage constraints.
    # We only enforce minimum requirements, allowing more assignments if needed
    slack_variables = {}  # Dictionary to store all slack variables
    
    for d in range(1, num_days + 1):
         for shift_code, req in required_shifts.items():
              # Skip split shifts (optional) here.
              if req.get("optional", False):
                   continue
              # Only enforce minimum requirements, remove upper bounds
              solver.Add(sum(x[(emp["id"], d, shift_code)] for emp in employees) >= req["total"])
              
              # Enforce qualification lower bounds (if applicable) with slack variables
              if "fach" in req:
                   # Create slack variable for fach requirement
                   fach_slack = solver.NumVar(0, solver.infinity(), f"fach_slack_{d}_{shift_code}")
                   slack_variables[(d, shift_code, "fach")] = fach_slack
                   solver.Add(
                        sum(x[(emp["id"], d, shift_code)] for emp in employees 
                            if employee_qualifications.get(emp["id"]) in fach_qual)
                        + fach_slack >= req["fach"]
                   )
              if "nonfach" in req:
                   # Create slack variable for non-fach requirement
                   nonfach_slack = solver.NumVar(0, solver.infinity(), f"nonfach_slack_{d}_{shift_code}")
                   slack_variables[(d, shift_code, "nonfach")] = nonfach_slack
                   solver.Add(
                        sum(x[(emp["id"], d, shift_code)] for emp in employees 
                            if employee_qualifications.get(emp["id"]) not in fach_qual)
                        + nonfach_slack >= req["nonfach"]
                   )

    # Group-level Early and Late Shift Coverage Constraints with slack variables
    early_shifts = {"B Dienst", "C Dienst", "BS Dienst", "C4 Dienst"}
    late_shifts  = {"S Dienst", "VS Dienst", "BS Dienst", "C4 Dienst"}
    pure_late_shifts = {"S Dienst", "VS Dienst"}  # Late shifts without split shifts
    
    for d in range(1, num_days + 1):
         current_date = datetime.date(year, month, d)
         is_weekend = current_date.weekday() >= 5
         
         # Early group coverage slack
         early_slack = solver.NumVar(0, solver.infinity(), f"early_slack_{d}")
         slack_variables[(d, "early")] = early_slack
         # Apply different minimum requirements for weekdays and weekends
         min_early_total = MIN_EARLY_TOTAL_WEEKEND if is_weekend else MIN_EARLY_TOTAL_WEEKDAY
         solver.Add(sum(x[(emp["id"], d, s)] for s in early_shifts for emp in employees) + early_slack >= min_early_total)
         
         # Early fach requirement slack
         early_fach_slack = solver.NumVar(0, solver.infinity(), f"early_fach_slack_{d}")
         slack_variables[(d, "early_fach")] = early_fach_slack
         solver.Add(sum(x[(emp["id"], d, s)] 
                       for s in early_shifts 
                       for emp in employees 
                       if employee_qualifications.get(emp["id"]) in fach_qual)
                   + early_fach_slack >= MIN_EARLY_FACH)
         
         # Late group coverage slack
         late_slack = solver.NumVar(0, solver.infinity(), f"late_slack_{d}")
         slack_variables[(d, "late")] = late_slack
         solver.Add(sum(x[(emp["id"], d, s)] for s in late_shifts for emp in employees) + late_slack >= MIN_LATE_TOTAL)
         
         # Late HF requirement slack
         late_hf_slack = solver.NumVar(0, solver.infinity(), f"late_hf_slack_{d}")
         slack_variables[(d, "late_hf")] = late_hf_slack
         solver.Add(sum(x[(emp["id"], d, s)] 
                       for s in late_shifts 
                       for emp in employees 
                       if employee_qualifications.get(emp["id"]) == "HF")
                   + late_hf_slack >= MIN_LATE_HF)
         
         # Soft constraint: Prefer only one fachpersonal in pure late shifts
         late_extra_fach_slack = solver.NumVar(0, solver.infinity(), f"late_extra_fach_{d}")
         slack_variables[(d, "late_extra_fach")] = late_extra_fach_slack
         solver.Add(sum(x[(emp["id"], d, s)] 
                       for s in pure_late_shifts 
                       for emp in employees 
                       if employee_qualifications.get(emp["id"]) in fach_qual)
                   - 1 <= late_extra_fach_slack)

         # Individual Minimum: At least 2 assignments for B Dienst per day with slack
         b_dienst_slack = solver.NumVar(0, solver.infinity(), f"b_dienst_slack_{d}")
         slack_variables[(d, "b_dienst")] = b_dienst_slack
         solver.Add(sum(x[(emp["id"], d, "B Dienst")] for emp in employees) + b_dienst_slack >= MIN_B_DIENST)

    # ------------------------------------------
    # Late-to-Early Shift Transition Constraints:
    # Only VS->C and C4->C transitions are allowed for late to early shifts
    for d in range(1, num_days):
         for emp in employees:
              e_id = emp["id"]
              # For all late shifts except VS and C4, no early shift is allowed the next day
              for late_shift in {"S Dienst", "BS Dienst"}:
                   for early_shift in early_shifts:
                        solver.Add(x[(e_id, d, late_shift)] + x[(e_id, d+1, early_shift)] <= 1)
              
              # VS can only transition to C Dienst
              solver.Add(x[(e_id, d, "VS Dienst")] + 
                        sum(x[(e_id, d+1, s)] for s in early_shifts if s != "C Dienst") <= 1)
              
              # C4 can only transition to C Dienst
              solver.Add(x[(e_id, d, "C4 Dienst")] + 
                        sum(x[(e_id, d+1, s)] for s in early_shifts if s != "C Dienst") <= 1)

    # ------------------------------------------
    # Weekend constraints: Limit each employee to at most 2 worked weekends per month.
    # A weekend is defined as a group of consecutive weekend days (Saturday and Sunday).
    weekend_groups = []
    handled = set()
    for d in range(1, num_days + 1):
         current_date = datetime.date(year, month, d)
         if current_date.weekday() in (5, 6) and d not in handled:
              group = [d]
              handled.add(d)
              # If day is Saturday and next day is Sunday, group them.
              if current_date.weekday() == 5 and d+1 <= num_days and datetime.date(year, month, d+1).weekday() == 6:
                  group.append(d+1)
                  handled.add(d+1)
              weekend_groups.append(group)

    # Create binary variable weekend_worked[(employee_id, weekend_index)] that equals 1 if the employee
    # works on any day in that weekend group.
    weekend_worked = {}
    for emp in employees:
         e_id = emp["id"]
         for w_idx, group in enumerate(weekend_groups):
              weekend_worked[(e_id, w_idx)] = solver.BoolVar(f"{e_id}_weekend_{w_idx}")

    # For each employee and each weekend group, if a shift is assigned on any day of that weekend,
    # then set the weekend_worked variable to 1.
    for emp in employees:
         e_id = emp["id"]
         for w_idx, group in enumerate(weekend_groups):
              for d in group:
                   for s in required_shifts.keys():
                        # If assigned a shift on day d, then weekend_worked must be 1.
                        solver.Add(x[(e_id, d, s)] <= weekend_worked[(e_id, w_idx)])

    # Now, limit the total worked weekends per employee to at most 2.
    for emp in employees:
         e_id = emp["id"]
         solver.Add(sum(weekend_worked[(e_id, w_idx)] for w_idx in range(len(weekend_groups))) <= MAX_WEEKENDS)

    # ------------------------------------------
    # Lehrling Constraints:
    # For Lehrlinge with qualification "Ausbildung 1":
    #   - They are allowed to work only on weekdays.
    #   - They can only be assigned to "B Dienst" or "C Dienst".
    for d in range(1, num_days + 1):
         current_date = datetime.date(year, month, d)
         for emp in employees:
              e_id = emp["id"]
              if employee_qualifications.get(e_id) in {"Ausbildung 1", "Ausbildung 2"}:
                   # If it's a weekend, no shifts allowed
                   if current_date.weekday() >= 5:
                        for s in required_shifts.keys():
                             solver.Add(x[(e_id, d, s)] == 0)
                   else:
                        # On weekdays, only B Dienst or C Dienst allowed
                        for s in required_shifts.keys():
                             if s not in {"B Dienst", "C Dienst"}:
                                  solver.Add(x[(e_id, d, s)] == 0)

    # For Lehrlinge with qualification "Ausbildung 2":
    for emp in employees:
         e_id = emp["id"]
         if employee_qualifications.get(e_id) == "Ausbildung 2":
              # Limit worked weekends to at most 1 (override default 2 weekend limit).
              solver.Add(sum(weekend_worked[(e_id, w_idx)] for w_idx in range(len(weekend_groups))) <= MAX_WEEKENDS_AUSB2)

              # Limit work on Sundays or Feiertage (holidays) to at most 1 day per month.
              sunday_or_holiday_work = []
              for d in range(1, num_days + 1):
                   current_date = datetime.date(year, month, d)
                   if current_date.weekday() == 6 or current_date in ch_holidays:
                        # Each day is either worked (1) or not (0) since max one shift per day.
                        sunday_or_holiday_work.append(sum(x[(e_id, d, s)] for s in required_shifts.keys()))
              if sunday_or_holiday_work:
                   solver.Add(sum(sunday_or_holiday_work) <= 1)

    # ------------------------------------------
    # Split Shift Constraints:
    # 1. For each day, the total number of split shift assignments (BS Dienst and C4 Dienst)
    #    across all employees must be at most 3.
    # 2. Only PH and HF are allowed to be assigned split shifts.
    for d in range(1, num_days + 1):
         # Limit total split shifts per day
         solver.Add(sum(x[(emp["id"], d, "BS Dienst")] + x[(emp["id"], d, "C4 Dienst")] 
                       for emp in employees) <= MAX_SPLIT_SHIFTS)
         
         # Only PH and HF can work split shifts
         for emp in employees:
              e_id = emp["id"]
              if employee_qualifications.get(e_id) not in {"PH", "HF"}:
                   solver.Add(x[(e_id, d, "BS Dienst")] == 0)
                   solver.Add(x[(e_id, d, "C4 Dienst")] == 0)

    # ------------------------------------------
    # Consecutive Shift Constraints (soft):
    # It is preferred to have consecutive shifts, but no more than 5 in a row.
    # After 5 consecutive shifts, there must be at least 2 days off.
    # For each employee and each window of 5 consecutive days (days d to d+4),
    # we introduce a binary variable Z[(e_id, d)] that equals 1 if the employee works all days in that block.
    # Then, if Z[(e_id, d)] = 1, we force the employee to be off on days d+5 and d+6.
    consecutive_block = {}
    consecutive_violation = {}  # Slack variables for violations
    
    for emp in employees:
         e_id = emp["id"]
         for d in range(1, num_days - 4 + 1):  # d from 1 to num_days-4
              # Create the binary variable for a full 5-day block starting at day d
              Z = solver.BoolVar(f"{e_id}_consec_{d}")
              consecutive_block[(e_id, d)] = Z
              
              # Create slack variable for violations
              V = solver.NumVar(0, solver.infinity(), f"{e_id}_violation_{d}")
              consecutive_violation[(e_id, d)] = V
              
              # Calculate the sum of shifts for all 5 days in the block
              block_sum = sum(sum(x[(e_id, day, s)] for s in required_shifts.keys()) 
                            for day in range(d, d+5))
              
              # If all 5 days are worked, Z must be 1
              solver.Add(5 * Z <= block_sum)
              # If not all 5 days are worked, Z must be 0
              solver.Add(block_sum <= 4 + Z)
              
              # If Z is 1 (all 5 days worked), the next two days should be off
              # Use slack variable for violations
              if d + 5 <= num_days:
                   solver.Add(sum(x[(e_id, d+5, s)] for s in required_shifts.keys()) <= 1 - Z + V)
              if d + 6 <= num_days:
                   solver.Add(sum(x[(e_id, d+6, s)] for s in required_shifts.keys()) <= 1 - Z + V)

    # ------------------------------------------
    # Target Workday Constraints (soft):
    # Each employee should work close to their target number of workdays
    workday_deviation_under = {}  # Slack variables for working less than target
    workday_deviation_over = {}   # Slack variables for working more than target
    workday_deviation_excessive = {}  # Slack variables for excessive overwork
    
    # Helper function to check if an employee has a specific absence type on a given day
    def has_absence_type(e_id, day, month, absences, absence_type):
        if e_id not in absences:
            return False
        for record in absences[e_id]:
            # record[0] is a date string in the format "DD.MM." (e.g. "7.2.")
            # record[1] is the absence type
            parts = record[0].split('.')
            if len(parts) >= 2:
                try:
                    absence_day = int(parts[0])
                    absence_month = int(parts[1])
                    if absence_day == day and absence_month == month and record[1] == absence_type:
                        return True
                except ValueError:
                    continue
        return False
    
    for emp in employees:
        e_id = emp["id"]
        target_days = employee_workload.get(e_id, 0)
        
        # Create slack variables for this employee
        under = solver.NumVar(0, solver.infinity(), f"{e_id}_under_target")
        over = solver.NumVar(0, solver.infinity(), f"{e_id}_over_target")
        excessive = solver.NumVar(0, solver.infinity(), f"{e_id}_excessive_over")
        workday_deviation_under[e_id] = under
        workday_deviation_over[e_id] = over
        workday_deviation_excessive[e_id] = excessive
        
        # Total shifts worked by this employee in the month
        total_shifts = sum(x[(e_id, d, s)] for d in range(1, num_days + 1) 
                         for s in required_shifts.keys())
        
        # For Leitung, include Bü Dienst in the total
        if employee_qualifications.get(e_id) == "Leitung":
            total_shifts += sum(y[(e_id, d)] for d in range(1, num_days + 1))
        
        # Count Ferien (Fe) and Schule (SL) as workdays
        total_absences = sum(1 for d in range(1, num_days + 1) 
                           if has_absence_type(e_id, d, month, absences, "Fe") or 
                              has_absence_type(e_id, d, month, absences, "SL"))
        
        # The difference between actual and target should equal the slack variables
        # Include both shifts worked and counted absences
        solver.Add(total_shifts + total_absences + under - over == target_days)
        
        # Any days over target count as excessive
        solver.Add(over <= excessive)

    # Initialize the objective function
    objective = solver.Objective()

    # Add penalties for coverage slack variables
    for d in range(1, num_days + 1):
        # Qualification requirements (highest priority)
        for shift_code in required_shifts.keys():
            if (d, shift_code, "fach") in slack_variables:
                objective.SetCoefficient(slack_variables[(d, shift_code, "fach")], FACH_PENALTY)
            if (d, shift_code, "nonfach") in slack_variables:
                objective.SetCoefficient(slack_variables[(d, shift_code, "nonfach")], NONFACH_PENALTY)
        
        # Group coverage requirements (high priority)
        if (d, "early") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "early")], EARLY_COVERAGE_PENALTY)
        if (d, "early_fach") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "early_fach")], EARLY_FACH_PENALTY)
        if (d, "late") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "late")], LATE_COVERAGE_PENALTY)
        if (d, "late_hf") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "late_hf")], LATE_HF_PENALTY)
        if (d, "b_dienst") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "b_dienst")], B_DIENST_PENALTY)
        
        # Soft constraint for extra fachpersonal in late shifts (low priority)
        if (d, "late_extra_fach") in slack_variables:
            objective.SetCoefficient(slack_variables[(d, "late_extra_fach")], EXTRA_FACH_LATE_PENALTY)
    
    # Regular assignment costs with shift preferences
    for d in range(1, num_days + 1):
        for shift_code in required_shifts.keys():
            for emp in employees:
                e_id = emp["id"]
                # Apply different costs based on shift type
                if shift_code in {"B Dienst", "C Dienst"}:
                    objective.SetCoefficient(x[(e_id, d, shift_code)], EARLY_SHIFT_COST)
                elif shift_code in {"S Dienst", "VS Dienst"}:
                    objective.SetCoefficient(x[(e_id, d, shift_code)], LATE_SHIFT_COST)
                else:  # Split shifts
                    objective.SetCoefficient(x[(e_id, d, shift_code)], SPLIT_SHIFT_COST)
    
    # Penalties for consecutive shift violations
    for emp in employees:
        e_id = emp["id"]
        for d in range(1, num_days - 4 + 1):
            objective.SetCoefficient(consecutive_violation[(e_id, d)], CONSECUTIVE_SHIFT_PENALTY)
    
    # Add penalties for workday target deviations
    for emp in employees:
        e_id = emp["id"]
        # Penalize under deviations
        objective.SetCoefficient(workday_deviation_under[e_id], WORKDAY_DEVIATION_PENALTY)
        # Heavy penalty for any days over target
        objective.SetCoefficient(workday_deviation_excessive[e_id], EXCESSIVE_WORKDAY_PENALTY)

    objective.SetMinimization()

    # Solve with a longer time limit
    solver.SetTimeLimit(60000)  # 60 seconds
    status = solver.Solve()

    # Check if a solution was found (accepting both optimal and feasible solutions)
    if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
        # Extract solution
        solution_values = []
        print(f"Number of variables in variable_names: {len(variable_names)}")
        print(f"First few variable_names: {variable_names[:5]}")
        for var_tuple in variable_names:
            if var_tuple[2] == "Bü Dienst":
                solution_values.append(y[(var_tuple[0], var_tuple[1])].solution_value())
            else:
                solution_values.append(x[var_tuple].solution_value())
        print(f"Number of solution values: {len(solution_values)}")
        return ScheduleSolution(solution_values)
    else:
        print("No optimal solution found.")
        return None
