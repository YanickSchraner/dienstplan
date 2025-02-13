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
    A very basic schedule generator using OR-Tools that enforces only the fundamental shift
    qualification constraints (Qualifikation pro Schicht).

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
    # Create the solver. Using CBC since it supports mixed-integer programming.
    solver = pywraplp.Solver.CreateSolver('CBC_MIXED_INTEGER_PROGRAMMING')
    if not solver:
        print("Solver not created.")
        return None

    num_days = calendar.monthrange(year, month)[1]
    
    # Define the required shifts and their counts along with qualification restrictions.
    # For each shift code, we specify:
    #   - "total": total number of assignments per day.
    #   - "fach": number of employees required with fach (qualified) for that shift.
    #   - "nonfach": number of employees required from non‑fach group.
    required_shifts = {
        "B Dienst": {"total": 3, "fach": 1, "nonfach": 2},
        "C Dienst": {"total": 2, "fach": 0, "nonfach": 2},
        "S Dienst": {"total": 2, "fach": 1, "nonfach": 1},
        "VS Dienst": {"total": 1},  # No qualification restrictions.
        "BS Dienst": {"total": 0, "optional": True},  # Split shift (optional).
        "C4 Dienst": {"total": 0, "optional": True}   # Split shift (optional).
    }
    
    # Define which qualifications count as fach (qualified).
    fach_qual = {"HF", "Leitung"}

    # Create binary decision variables for each employee/day/shift.
    x = {}
    global variable_names
    variable_names = []  # Reset global variable_names list.
    
    for d in range(1, num_days + 1):
        for shift_code in required_shifts.keys():
            for emp in employees:
                e_id = emp["id"]
                var = solver.BoolVar(f"{e_id}_{d}_{shift_code}")
                x[(e_id, d, shift_code)] = var
                variable_names.append((e_id, d, shift_code))
    
    # Constraint: Each employee can work at most one shift per day.
    for d in range(1, num_days + 1):
        for emp in employees:
            e_id = emp["id"]
            solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) <= 1)
    
    # ------------------------------------------
    # Availability constraints: an employee who is absent on a day
    # cannot be assigned any shift.
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

    for d in range(1, num_days + 1):
         for emp in employees:
             e_id = emp["id"]
             if employee_is_absent(e_id, d, month, absences):
                 solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)

    # Enforce that Leitungs employees can only be assigned to "B Dienst"
    # as a regular shift (they may also be assigned to a Bü Dienst, handled later).
    for d in range(1, num_days + 1):
         for emp in employees:
             e_id = emp["id"]
             if employee_qualifications.get(e_id) == "Leitung":
                 for shift_code in required_shifts.keys():
                     if shift_code != "B Dienst":
                         solver.Add(x[(e_id, d, shift_code)] == 0)

    # For each day and for each non-optional shift code, set individual coverage constraints.
    # We relax these to an upper bound so that split shifts can substitute.
    for d in range(1, num_days + 1):
         for shift_code, req in required_shifts.items():
              # Skip split shifts (optional) here.
              if req.get("optional", False):
                   continue
              # Enforce an upper bound on assignments for this shift.
              solver.Add(sum(x[(emp["id"], d, shift_code)] for emp in employees) <= req["total"])
              
              # Enforce qualification lower bounds (if applicable).
              if "fach" in req:
                   solver.Add(
                        sum(x[(emp["id"], d, shift_code)] for emp in employees 
                            if employee_qualifications.get(emp["id"]) in fach_qual)
                        >= req["fach"]
                   )
              if "nonfach" in req:
                   solver.Add(
                        sum(x[(emp["id"], d, shift_code)] for emp in employees 
                            if employee_qualifications.get(emp["id"]) not in fach_qual)
                        >= req["nonfach"]
                   )

    # ------------------------------------------
    # Group-level Early and Late Shift Coverage Constraints (relaxed):
    # Define early shifts as: B Dienst, C Dienst, BS Dienst, C4 Dienst.
    # Define late shifts  as: S Dienst, VS Dienst, BS Dienst, C4 Dienst.
    early_shifts = {"B Dienst", "C Dienst", "BS Dienst", "C4 Dienst"}
    late_shifts  = {"S Dienst", "VS Dienst", "BS Dienst", "C4 Dienst"}
    for d in range(1, num_days + 1):
         # At least 5 employees must cover the early shift group.
         solver.Add(sum(x[(emp["id"], d, s)] for s in early_shifts for emp in employees) >= 5)
         # At least 3 employees must cover the late shift group.
         solver.Add(sum(x[(emp["id"], d, s)] for s in late_shifts for emp in employees) >= 3)

         # Additionally, enforce individual minimums:
         # At least 2 assignments for B Dienst per day.
         solver.Add(sum(x[(emp["id"], d, "B Dienst")] for emp in employees) >= 2)
         # At least 1 assignment for S Dienst per day.
         solver.Add(sum(x[(emp["id"], d, "S Dienst")] for emp in employees) >= 1)

    # ------------------------------------------
    # Late-to-Early Shift Transition Constraints (including split shifts):
    # A split shift counts both as an early and as a late shift.
    # Therefore, if an employee works any "late" or "split" shift on day d,
    # they are considered to have worked a late shift.
    # Then on day d+1, if the employee is assigned an early shift, the following disallowed transitions apply:
    #    For "B Dienst" on day d+1, none of the shifts
    #         { "S Dienst", "VS Dienst", "BS Dienst", "C4 Dienst" }
    #         is allowed on day d.
    #    For "C Dienst" on day d+1, if the employee worked "S Dienst" or "BS Dienst" on day d then the transition is disallowed.
    for d in range(1, num_days):
         for emp in employees:
              e_id = emp["id"]
              # Disallow any late assignment (including split shifts) on day d followed by "B Dienst" on day d+1.
              solver.Add( x[(e_id, d, "S Dienst")]
                          + x[(e_id, d, "VS Dienst")]
                          + x[(e_id, d, "BS Dienst")]
                          + x[(e_id, d, "C4 Dienst")]
                          + x[(e_id, d+1, "B Dienst")] <= 1 )

              # Disallow if employee works "S Dienst" or a split shift of type "BS Dienst" on day d,
              # then "C Dienst" is disallowed on day d+1.
              solver.Add( x[(e_id, d, "S Dienst")]
                          + x[(e_id, d, "BS Dienst")]
                          + x[(e_id, d+1, "C Dienst")] <= 1 )

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
         solver.Add(sum(weekend_worked[(e_id, w_idx)] for w_idx in range(len(weekend_groups))) <= 2)

    # ------------------------------------------
    # Lehrling Constraints:
    # For Lehrlinge with qualification "Ausbildung 1":
    #   - They are allowed to work only on weekdays.
    #   - They can only be assigned to "B Dienst" or "C Dienst".
    # for d in range(1, num_days + 1):
    #      current_date = datetime.date(year, month, d)
    #      for emp in employees:
    #           e_id = emp["id"]
    #           if employee_qualifications.get(e_id) == "Ausbildung 1":
    #                # Force no assignments on weekends.
    #                if current_date.weekday() >= 5:
    #                     solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)
    #                else:
    #                     # On weekdays, force shifts other than "B Dienst" or "C Dienst" to 0.
    #                     for shift_code in required_shifts.keys():
    #                          if shift_code not in {"B Dienst", "C Dienst"}:
    #                               solver.Add(x[(e_id, d, shift_code)] == 0)

    # For Lehrlinge with qualification "Ausbildung 2":
    for emp in employees:
         e_id = emp["id"]
         if employee_qualifications.get(e_id) == "Ausbildung 2":
              # Limit worked weekends to at most 1 (override default 2 weekend limit).
              solver.Add(sum(weekend_worked[(e_id, w_idx)] for w_idx in range(len(weekend_groups))) <= 1)

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
    # Split Shift Constraint:
    # For each day, the total number of split shift assignments (BS Dienst and C4 Dienst)
    # across all employees must be at most 3.
    for d in range(1, num_days + 1):
         solver.Add(sum(x[(emp["id"], d, "BS Dienst")] + x[(emp["id"], d, "C4 Dienst")] for emp in employees) <= 3)

    # ------------------------------------------
    # Consecutive Shift Constraints:
    # It is not permitted to have more than 5 consecutive working days.
    # Moreover, any block of 5 consecutive working days must be
    # followed by at least two days off.
    # For each employee and each window of 5 consecutive days (days d to d+4),
    # we introduce a binary variable Z[(e_id, d)] that equals 1 if the employee works all days in that block.
    # Then, if Z[(e_id, d)] = 1, we force the employee to be off on days d+5 and d+6.
    consecutive_block = {}
    for emp in employees:
         e_id = emp["id"]
         for d in range(1, num_days - 4 + 1):  # d from 1 to num_days-4
              # Create the binary variable for a full 5-day block starting at day d.
              Z = solver.BoolVar(f"{e_id}_consec_{d}")
              consecutive_block[(e_id, d)] = Z
              # For each day in the block, count any shift (including split shifts) as work.
              for j in range(d, d+5):
                   solver.Add( Z <= sum(x[(e_id, j, s)] for s in required_shifts.keys()) )
              solver.Add( Z >= sum(x[(e_id, j, s)] for s in required_shifts.keys()) - 4 )
              if d + 5 <= num_days:
                   solver.Add( sum(x[(e_id, d+5, s)] for s in required_shifts.keys()) <= 1 - Z )
              if d + 6 <= num_days:
                   solver.Add( sum(x[(e_id, d+6, s)] for s in required_shifts.keys()) <= 1 - Z )

    # ------------------------------------------
    # Additional constraints for Leitung employees.
    # ------------------------------------------
    # Create binary decision variables for "Bü Dienst" (office shift) for each employee and each day.
    y = {}
    for d in range(1, num_days + 1):
        current_date = datetime.date(year, month, d)
        for emp in employees:
            e_id = emp["id"]
            var_y = solver.BoolVar(f"{e_id}_{d}_Bü Dienst")
            y[(e_id, d)] = var_y
            # If the day is weekend, the employee is not "Leitung",
            # or the employee is absent on that day, force Bü Dienst to 0.
            if current_date.weekday() >= 5 or employee_qualifications.get(e_id) != "Leitung" \
               or employee_is_absent(e_id, d, month, absences):
                solver.Add(var_y == 0)

    # For Leitungs employees on weekdays: they can work either a regular shift or Bü Dienst (but not both).
    for d in range(1, num_days + 1):
        current_date = datetime.date(year, month, d)
        if current_date.weekday() < 5:  # Weekday
            for emp in employees:
                e_id = emp["id"]
                if employee_qualifications.get(e_id) == "Leitung":
                    solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) + y[(e_id, d)] <= 1)

    # For each Leitungs employee, enforce that they do not work on weekends (from regular shifts).
    for d in range(1, num_days + 1):
        current_date = datetime.date(year, month, d)
        if current_date.weekday() >= 5:  # Weekend
            for emp in employees:
                e_id = emp["id"]
                if employee_qualifications.get(e_id) == "Leitung":
                    solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)

    # For each Leitungs employee, enforce exactly 4 Bü Dienst assignments on weekdays in the month.
    for emp in employees:
        e_id = emp["id"]
        if employee_qualifications.get(e_id) == "Leitung":
            solver.Add(sum(y[(e_id, d)] for d in range(1, num_days + 1)
                           if datetime.date(year, month, d).weekday() < 5) == 4)

    # Set a dummy objective (we only require feasibility).
    objective = solver.Objective()
    objective.SetMinimization()
    # (Since no cost coefficients are provided, the objective remains zero.)
    
    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        print("No optimal solution found.")
        return None
    
    # Append Bü Dienst variables for Leitung employees to variable_names,
    # so they are extracted in the solution.
    for d in range(1, num_days + 1):
         for emp in employees:
             e_id = emp["id"]
             # Only add Bü Dienst variable if the employee is Leitung and if it's a weekday.
             if employee_qualifications.get(e_id) == "Leitung" and datetime.date(year, month, d).weekday() < 5:
                 variable_names.append((e_id, d, "Bü Dienst"))

    # Collect solution variable values in the order of variable_names.
    col_values = []
    for var_name in variable_names:
         # If the variable refers to a Bü Dienst, get the value from y,
         # otherwise get it from the x dictionary.
         if var_name[2] == "Bü Dienst":
             col_values.append(y[(var_name[0], var_name[1])].solution_value())
         else:
             col_values.append(x[var_name].solution_value())
    
    return ScheduleSolution(col_values)
