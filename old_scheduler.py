import calendar
from datetime import date, datetime, timedelta
import logging
from typing import List, Dict, Tuple, Any
import highspy
import numpy as np

from highspy import (
    Highs,
    HighsStatus,
    HighsModelStatus,
    ObjSense,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Constants for variable types
kInteger = 1  # Integer variable type constant for HiGHS

variable_names = []  # Global variable to store variable names

def is_absent(employee_id: str, day: str, absences: Dict[str, List[Tuple[str, str]]]) -> bool:
    """Check if an employee is absent on a given day."""
    if employee_id in absences:
        for absence_day_str, _ in absences[employee_id]:
            if absence_day_str.split(".")[0] == day:
                return True
    return False

def generate_schedule_highs(
    employees: List[Dict[str, Any]],
    shifts: List[Dict[str, Any]],
    absences: Dict[str, List[Tuple[str, str]]],
    employee_qualifications: Dict[str, str],
    employee_workload: Dict[str, int],
    year: int,
    month: int,
    ch_holidays: List[date],
):
    """
    Generates a schedule using HiGHS.

    Args:
        employees: List of employee dictionaries (id, qualifikation).
        shifts: List of shift dictionaries (code).
        absences: Dictionary of employee absences (employee_id: [(date_str, type)]).
        employee_qualifications: Dictionary of employee qualifications (employee_id: qualifikation).
        employee_workload: Dictionary of employee target workloads (employee_id: target_days).
        year: Year for the schedule.
        month: Month for the schedule.
        ch_holidays: List of holidays (as datetime.date objects).

    Returns:
        The Highs Solution object
    """
    global variable_names  # Declare we'll use the global variable
    variable_names = []  # Reset the variable names list
    
    logging.info(f"Generating schedule for {calendar.month_name[month]} {year}")
    num_days = calendar.monthrange(year, month)[1]
    days = [str(day) for day in range(1, num_days + 1)]

    model = Highs()
    model.setOptionValue("log_to_console", True)
    # Add these options for infeasibility analysis
    model.setOptionValue("presolve", "on")
    model.setOptionValue("mip_detect_symmetry", "on")
    model.setOptionValue("iis", "on")  # Turn on IIS computation
    model.setOptionValue("log_dev_level", 3)  # Increase logging detail
    model.setOptionValue("mip_rel_gap", 0.01)  # Set a 1% relative gap tolerance

    # --- Variables ---
    variables = {}  # Store variable names and their corresponding HiGHS indices.
    variable_types = []
    lower_bounds = []
    upper_bounds = []

    # Define which shifts are assignable (not absences)
    assignable_shift_codes = [
        "B Dienst", "C Dienst", "VS Dienst", "S Dienst", 
        "BS Dienst", "C4 Dienst", "Bü Dienst"  # Remove "x" from here
    ]
    
    def is_absent_on_day(employee_id, day_str):
        """Helper function to check if employee is absent on a given day"""
        if employee_id not in absences:
            return False
        return any(absence_day_str.split(".")[0] == day_str 
                  for absence_day_str, _ in absences[employee_id])

    num_vars = 0
    for employee in employees:
        for day in days:
            # Skip creating any variables if employee is absent
            if is_absent_on_day(employee["id"], day):
                continue
                
            # Create variables only if employee is available
            variable_name = (employee["id"], day)
            variables[variable_name] = num_vars
            variable_names.append(variable_name)
            num_vars += 1

            # Create shift assignment variables
            for shift in shifts:
                if shift["code"] in assignable_shift_codes:
                    var_name_shift = (employee["id"], day, shift["code"])
                    variable_names.append(var_name_shift)
                    variable_types.append(kInteger)
                    lower_bounds.append(0)
                    upper_bounds.append(1)
                    num_vars += 1

    logging.info(f"Variables created: {variable_names}")

    # --- Objective Function (Minimize Deviation from Workload) ---
    objective_coeffs = np.zeros(num_vars, dtype=np.float64)
    lower_bounds = np.zeros(num_vars, dtype=np.float64)
    upper_bounds = np.ones(num_vars, dtype=np.float64)
    
    # Add variables to model
    model.addVars(num_vars, lower_bounds, upper_bounds)

    # --- Constraints ---
    # Initialize constraint arrays
    row_lower = []
    row_upper = []
    a_matrix_start = [0]
    a_matrix_index = []
    a_matrix_value = []

    # Add one-shift-per-day constraints
    logging.info("Adding one-shift-per-day constraints...")
    for employee in employees:
        for day in days:
            # Skip constraints for absent employees
            if is_absent_on_day(employee["id"], day):
                continue

            # Get indices for all shift variables for this employee-day
            shift_vars = []
            for shift in shifts:
                if shift["code"] in assignable_shift_codes:  # Only consider non-x shifts
                    var_name = (employee["id"], day, shift["code"])
                    if var_name in variable_names:
                        shift_vars.append(variable_names.index(var_name))
            
            if shift_vars:  # Only add constraint if we have variables
                # Add constraint: sum of shift variables <= 1 (allowing for no shift = x shift)
                for var_idx in shift_vars:
                    a_matrix_index.append(var_idx)
                    a_matrix_value.append(1.0)
                
                a_matrix_start.append(len(a_matrix_index))
                row_lower.append(0.0)  # Allow no shift
                row_upper.append(1.0)  # Maximum one shift

    # 1. Employee Workload (Soft Constraint - includes shifts, SL and Fe days)
    logging.info("Adding Workload Constraints...")

    for employee_id in employee_workload:
        target_days = employee_workload.get(employee_id, 0)
        
        # Count SL and Fe days for this employee
        workdays_from_absences = 0
        if employee_id in absences:
            workdays_from_absences = sum(1 for _, absence_type in absences[employee_id] 
                                       if absence_type in ["SL", "Fe"])
        
        # Get variables for all assignable shifts
        shift_vars = []
        for day in days:
            # Skip if employee is absent (but not for SL/Fe)
            if is_absent_on_day(employee_id, day):
                absence_type = next((type_ for date_, type_ in absences[employee_id] 
                                   if date_.split(".")[0] == day), None)
                if absence_type not in ["SL", "Fe"]:
                    continue
            
            for shift in shifts:
                if shift["code"] in assignable_shift_codes:  # Only consider assignable shifts
                    var_name = (employee_id, day, shift['code'])
                    if var_name in variable_names:  # Check if variable exists
                        var_index = variable_names.index(var_name)
                        shift_vars.append(var_index)

        # Add soft penalties to objective function
        if shift_vars:  # Only if we have shifts to assign
            remaining_target = max(0, target_days - workdays_from_absences)
            
            if remaining_target > 0:
                # Only penalize being over target (+10 per day over)
                for var_index in shift_vars:
                    objective_coeffs[var_index] += 10.0/remaining_target  # Discourage exceeding target

        # Special handling for Büro Tage (if employee is Leitung)
        if employee_qualifications.get(employee_id) == "Leitung":
            buro_tage_target = 4  # Target number of Büro Tage per month
            buro_vars = []
            for day in days:
                if not is_absent_on_day(employee_id, day):
                    var_name = (employee_id, day, "Bü Dienst")
                    if var_name in variable_names:
                        var_index = variable_names.index(var_name)
                        buro_vars.append(var_index)
                        objective_coeffs[var_index] += -8.0/buro_tage_target  # Encourage reaching Büro target

    logging.info("Workload Constraints Added to Objective.")

    # 2. Qualification per Shift TYPE
    early_shifts = ["B Dienst", "C Dienst"]
    late_shifts = ["VS Dienst", "S Dienst"]
    split_shifts = ["BS Dienst", "C4 Dienst"]
    all_early_type_shifts = early_shifts + split_shifts
    all_late_type_shifts = late_shifts + split_shifts

    logging.info("Adding Shift Requirements...")
    for day in days:
        # --- Early Shift Requirements ---
        # 1. Total early shift staffing
        early_fach_vars = []
        early_nicht_fach_vars = []
        for employee in employees:
            # Regular early shifts and split shifts
            for shift in early_shifts + split_shifts:
                var_name = (employee["id"], day, shift)
                if var_name in variable_names:
                    var_index = variable_names.index(var_name)
                    if employee_qualifications.get(employee["id"]) in ("HF", "Leitung"):
                        early_fach_vars.append(var_index)
                    else:  # PH or Ausbildung
                        early_nicht_fach_vars.append(var_index)

        # Constraint: 1-2 Fachpersonen in early shifts
        if early_fach_vars:
            for var_index in early_fach_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(1.0)  # Minimum 1 Fachperson
            row_upper.append(2.0)  # Maximum 2 Fachpersonen

        # Constraint: 4-6 nicht Fachpersonen in early shifts
        if early_nicht_fach_vars:
            for var_index in early_nicht_fach_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(4.0)  # Minimum 4 nicht Fachpersonen
            row_upper.append(6.0)  # Maximum 6 nicht Fachpersonen

        # 2. B Dienst specific requirements
        b_dienst_vars = []
        b_dienst_hf_vars = []
        for employee in employees:
            var_name = (employee["id"], day, "B Dienst")
            if var_name in variable_names:
                var_index = variable_names.index(var_name)
                b_dienst_vars.append(var_index)
                if employee_qualifications.get(employee["id"]) == "HF":
                    b_dienst_hf_vars.append(var_index)

        # Constraint: Exactly 1 HF in B Dienst
        if b_dienst_hf_vars:
            for var_index in b_dienst_hf_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(1.0)
            row_upper.append(1.0)

        # Constraint: Minimum 3 people total in B Dienst
        if b_dienst_vars:
            for var_index in b_dienst_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(3.0)
            row_upper.append(float('inf'))

        # --- Late Shift Requirements ---
        # New: Constraint: Exactly 1 HF in S Dienst for each day
        s_dienst_hf_vars = []
        for employee in employees:
            if employee_qualifications.get(employee["id"]) == "HF":
                var_name = (employee["id"], day, "S Dienst")
                if var_name in variable_names:
                    s_dienst_hf_vars.append(variable_names.index(var_name))
        if s_dienst_hf_vars:
            for var_index in s_dienst_hf_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(1.0)
            row_upper.append(1.0)

        # Constraint: 2-3 Nicht Fachpersonen in late shifts (employees not HF)
        late_nicht_fach_vars = []
        for employee in employees:
            if employee_qualifications.get(employee["id"]) != "HF":
                for shift in late_shifts + split_shifts:
                    var_name = (employee["id"], day, shift)
                    if var_name in variable_names:
                        late_nicht_fach_vars.append(variable_names.index(var_name))
        if late_nicht_fach_vars:
            for var_index in late_nicht_fach_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(2.0)
            row_upper.append(3.0)

        # Split shift limit
        split_shift_vars = []
        for employee in employees:
            for shift in split_shifts:
                var_name = (employee["id"], day, shift)
                if var_name in variable_names:
                    var_index = variable_names.index(var_name)
                    split_shift_vars.append(var_index)
                    # Add penalty to discourage split shifts
                    objective_coeffs[var_index] += 200.0

        # Constraint: Maximum 3 split shifts per day
        if split_shift_vars:
            for var_index in split_shift_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(0.0)
            row_upper.append(3.0)

    logging.info("Shift Requirements Added.")

    # 3. Lehrling Constraint (Max 1 Sunday/Holiday per month)
    logging.info("Adding Lehrling Constraint for Ausbildung 2...")
    for employee in employees:
        if employee["qualifikation"] == "Ausbildung 2":
            sunday_holiday_vars = []
            for day_val in range(1, num_days + 1):
                day_str = str(day_val)
                date_obj = date(year, month, day_val)
                if date_obj.weekday() == 6 or date_obj in ch_holidays:
                    # Find the corresponding variable index
                    for shift in shifts:
                        var_name = (employee["id"], day_str, shift["code"])
                        if var_name in variable_names:  # Variable may not exist due to absences
                            sunday_holiday_vars.append(variable_names.index(var_name))
            if sunday_holiday_vars:
                for var_index in sunday_holiday_vars:
                    a_matrix_index.append(var_index)
                    a_matrix_value.append(1.0)
                a_matrix_start.append(len(a_matrix_index))
                row_lower.append(0.0)
                row_upper.append(1.0)
    logging.info("Lehrling Constraint Added.")

    # Additional constraints for Ausbildung 1:
    #   - They are not allowed to work on weekends (Saturday and Sunday)
    #   - On weekdays they are allowed only a B Dienst or C Dienst.
    logging.info("Adding constraints for Ausbildung 1: weekdays allowed only B or C Dienst and no weekend work")
    for employee in employees:
        if employee["qualifikation"] == "Ausbildung 1":
            for day_val in range(1, num_days + 1):
                day_str = str(day_val)
                if is_absent_on_day(employee["id"], day_str):
                    continue
                date_obj = date(year, month, day_val)
                if date_obj.weekday() >= 5:  # Weekend: block all shifts on Saturday and Sunday
                    block_vars = []
                    for shift in shifts:
                        if shift["code"] in assignable_shift_codes:
                            var_name = (employee["id"], day_str, shift["code"])
                            if var_name in variable_names:
                                block_vars.append(variable_names.index(var_name))
                    if block_vars:
                        for var_index in block_vars:
                            a_matrix_index.append(var_index)
                            a_matrix_value.append(1.0)
                        a_matrix_start.append(len(a_matrix_index))
                        row_lower.append(0.0)
                        row_upper.append(0.0)
                else:  # Weekday: allow only B Dienst or C Dienst
                    block_vars = []
                    for shift in shifts:
                        if shift["code"] not in ["B Dienst", "C Dienst"]:
                            var_name = (employee["id"], day_str, shift["code"])
                            if var_name in variable_names:
                                block_vars.append(variable_names.index(var_name))
                    if block_vars:
                        for var_index in block_vars:
                            a_matrix_index.append(var_index)
                            a_matrix_value.append(1.0)
                        a_matrix_start.append(len(a_matrix_index))
                        row_lower.append(0.0)
                        row_upper.append(0.0)
    logging.info("Ausbildung 1 constraints added.")

    # 4. Spät-Frühdienst Transition
    logging.info("Adding Spaet-Fruehdienst Constraint...")
    # Only allow VS->C and C4->C transitions
    allowed_transitions = {
        "VS Dienst": ["C Dienst"],
        "C4 Dienst": ["C Dienst"]
    }

    for employee in employees:
        for day_index in range(len(days) - 1):
            day = days[day_index]
            next_day = days[day_index + 1]

            if not is_absent(employee["id"], day, absences) and not is_absent(employee["id"], next_day, absences):
                for shift1 in shifts:
                    if shift1["code"] in late_shifts + split_shifts:  # Check all late-type shifts
                        for shift2 in shifts:
                            if shift2["code"] in early_shifts + split_shifts:  # Check all early-type shifts
                                # If it's not an allowed transition, add a large penalty
                                if (shift1["code"] not in allowed_transitions or 
                                    shift2["code"] not in allowed_transitions.get(shift1["code"], [])):
                                    var_name1 = (employee["id"], day, shift1["code"])
                                    var_name2 = (employee["id"], next_day, shift2["code"])

                                    if var_name1 in variable_names and var_name2 in variable_names:
                                        var_index1 = variable_names.index(var_name1)
                                        var_index2 = variable_names.index(var_name2)
                                        
                                        # Add a large penalty to discourage this transition
                                        objective_coeffs[var_index1] += 1000
                                        objective_coeffs[var_index2] += 1000

    # Add constraint: Only Leitung can have Bü Dienst and max 4 Bü Dienst per month
    logging.info("Adding Bü Dienst Constraints...")
    for employee in employees:
        if employee_qualifications.get(employee["id"]) == "Leitung":
            # --- Enforce aggregate Bü Dienst assignments ---
            # Count Bü Dienst shifts for this Leitung employee
            bu_dienst_vars = []
            for day in days:
                var_name = (employee["id"], day, "Bü Dienst")
                if var_name in variable_names:
                    var_index = variable_names.index(var_name)
                    bu_dienst_vars.append(var_index)
            
            # Enforce exactly 4 Bü Dienst per month for Leitung
            if bu_dienst_vars:
                for var_index in bu_dienst_vars:
                    a_matrix_index.append(var_index)
                    a_matrix_value.append(1.0)
                a_matrix_start.append(len(a_matrix_index))
                row_lower.append(4.0)
                row_upper.append(4.0)

            # --- For each day, enforce that Leitung works only on weekdays with either a B Dienst or Bü Dienst ---
            for day_val in range(1, num_days + 1):
                day_str = str(day_val)
                if is_absent_on_day(employee["id"], day_str):
                    continue
                date_obj = date(year, month, day_val)
                if date_obj.weekday() >= 5:
                    # Block all shifts on weekends for Leitung
                    for shift in shifts:
                        var_name = (employee["id"], day_str, shift["code"])
                        if var_name in variable_names:
                            var_index = variable_names.index(var_name)
                            a_matrix_index.append(var_index)
                            a_matrix_value.append(1.0)
                            a_matrix_start.append(len(a_matrix_index))
                            row_lower.append(0.0)
                            row_upper.append(0.0)
                else:
                    # Weekday: first, block any shift not in {"B Dienst", "Bü Dienst"}
                    for shift in shifts:
                        if shift["code"] not in ["B Dienst", "Bü Dienst"]:
                            var_name = (employee["id"], day_str, shift["code"])
                            if var_name in variable_names:
                                var_index = variable_names.index(var_name)
                                a_matrix_index.append(var_index)
                                a_matrix_value.append(1.0)
                                a_matrix_start.append(len(a_matrix_index))
                                row_lower.append(0.0)
                                row_upper.append(0.0)

                    # Then force that exactly one assignment among {"B Dienst", "Bü Dienst"} is made
                    allowed_indices = []
                    for shift_code in ["B Dienst", "Bü Dienst"]:
                        var_name = (employee["id"], day_str, shift_code)
                        if var_name in variable_names:
                            allowed_indices.append(variable_names.index(var_name))
                    if allowed_indices:
                        for var_index in allowed_indices:
                            a_matrix_index.append(var_index)
                            a_matrix_value.append(1.0)
                        a_matrix_start.append(len(a_matrix_index))
                        row_lower.append(1.0)
                        row_upper.append(1.0)
        else:
            # For non-Leitung employees, block Bü Dienst
            for day in days:
                var_name = (employee["id"], day, "Bü Dienst")
                if var_name in variable_names:
                    var_index = variable_names.index(var_name)
                    a_matrix_index.append(var_index)
                    a_matrix_value.append(1.0)
                    a_matrix_start.append(len(a_matrix_index))
                    row_lower.append(0.0)
                    row_upper.append(0.0)

    # 1. Weekend Limit Constraint
    logging.info("Adding Weekend Limit Constraint...")
    for employee in employees:
        weekend_shift_vars = []
        for day_val in range(1, num_days + 1):
            date_obj = date(year, month, day_val)
            if date_obj.weekday() >= 5:  # Saturday or Sunday
                day = str(day_val)
                for shift in shifts:
                    if shift["code"] in assignable_shift_codes:
                        var_name = (employee["id"], day, shift["code"])
                        if var_name in variable_names:
                            weekend_shift_vars.append(variable_names.index(var_name))
        
        if weekend_shift_vars:
            for var_index in weekend_shift_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(0.0)
            row_upper.append(4.0)  # Max 2 weekends = 4 weekend days

    # 2. Consecutive Shifts Constraint
    logging.info("Adding Consecutive Shifts Constraint...")
    for employee in employees:
        for start_day in range(1, num_days - 4):  # Check each 6-day window
            consecutive_shift_vars = []
            for day_offset in range(6):
                day = str(start_day + day_offset)
                for shift in shifts:
                    if shift["code"] in assignable_shift_codes:
                        var_name = (employee["id"], day, shift["code"])
                        if var_name in variable_names:
                            consecutive_shift_vars.append(variable_names.index(var_name))
            
            if consecutive_shift_vars:
                for var_index in consecutive_shift_vars:
                    a_matrix_index.append(var_index)
                    a_matrix_value.append(1.0)
                a_matrix_start.append(len(a_matrix_index))
                row_lower.append(0.0)
                row_upper.append(5.0)  # Max 5 consecutive shifts

    # 3. VS Dienst Limit
    logging.info("Adding VS Dienst Limit...")
    for day in days:
        vs_dienst_vars = []
        for employee in employees:
            var_name = (employee["id"], day, "VS Dienst")
            if var_name in variable_names:
                vs_dienst_vars.append(variable_names.index(var_name))
        
        if vs_dienst_vars:
            for var_index in vs_dienst_vars:
                a_matrix_index.append(var_index)
                a_matrix_value.append(1.0)
            a_matrix_start.append(len(a_matrix_index))
            row_lower.append(0.0)
            row_upper.append(1.0)  # Max 1 person in VS Dienst

    # Add constraints to model
    num_rows = len(row_lower)
    row_lower = np.array(row_lower, dtype=np.float64)
    row_upper = np.array(row_upper, dtype=np.float64)
    a_matrix_start = np.array(a_matrix_start, dtype=np.int32)
    a_matrix_index = np.array(a_matrix_index, dtype=np.int32)
    a_matrix_value = np.array(a_matrix_value, dtype=np.float64)

    model.addRows(num_rows, row_lower, row_upper, 
                 len(a_matrix_index), a_matrix_start, 
                 a_matrix_index, a_matrix_value)

    # Set objective
    model.changeObjectiveSense(ObjSense.kMinimize)

    # --- Add tie-break noise to prevent optimizer from ganging ---
    for idx, var_name in enumerate(variable_names):
        if isinstance(var_name, tuple) and len(var_name) == 3:
            # add a very small noise proportional to the index (deterministic)
            objective_coeffs[idx] += idx * 1e-6

    col_indices = np.arange(num_vars, dtype=np.int32)
    model.changeColsCost(num_vars, col_indices, objective_coeffs)

    # Solve model
    status = model.run()
    
    if model.getModelStatus() == HighsModelStatus.kInfeasible:
        logging.warning("Model is infeasible!")
        
        # Log constraint information
        logging.warning("\nAnalyzing constraints:")
        
        # Check early shift requirements
        logging.warning("\nEarly shift staffing per day:")
        for day in days:
            fach_count = sum(1 for emp in employees 
                           if emp["qualifikation"] in ("HF", "Leitung") 
                           and not is_absent_on_day(emp["id"], day))
            nicht_fach_count = sum(1 for emp in employees 
                                 if emp["qualifikation"] not in ("HF", "Leitung")
                                 and not is_absent_on_day(emp["id"], day))
            logging.warning(f"Day {day}:")
            logging.warning(f"  Available Fachpersonen: {fach_count} (Need 1-3)")
            logging.warning(f"  Available Nicht-Fachpersonen: {nicht_fach_count}")
        
        # Check late shift requirements
        logging.warning("\nLate shift staffing per day:")
        for day in days:
            fach_count = sum(1 for emp in employees 
                           if emp["qualifikation"] in ("HF", "Leitung")
                           and not is_absent_on_day(emp["id"], day))
            nicht_fach_count = sum(1 for emp in employees 
                                 if emp["qualifikation"] not in ("HF", "Leitung")
                                 and not is_absent_on_day(emp["id"], day))
            logging.warning(f"Day {day}:")
            logging.warning(f"  Available Fachpersonen: {fach_count} (Need 1-2)")
            logging.warning(f"  Available Nicht-Fachpersonen: {nicht_fach_count}")

        # Check workload feasibility
        logging.warning("\nWorkload analysis:")
        for emp in employees:
            emp_id = emp["id"]
            target_days = employee_workload.get(emp_id, 0)
            sl_days = 0
            fe_days = 0
            if emp_id in absences:
                sl_days = sum(1 for _, absence_type in absences[emp_id] if absence_type == "SL")
                fe_days = sum(1 for _, absence_type in absences[emp_id] if absence_type == "Fe")

            available_days = sum(1 for day in days 
                               if not is_absent_on_day(emp_id, day))
            logging.warning(f"Employee {emp_id}:")
            logging.warning(f"  Target workdays: {target_days}")
            logging.warning(f"  SL days: {sl_days}")
            logging.warning(f"  Fe days: {fe_days}")
            logging.warning(f"  Remaining target: {max(0, target_days - sl_days - fe_days)}")
            logging.warning(f"  Available days: {available_days}")


        # Check B Dienst coverage
        logging.warning("\nB Dienst coverage analysis:")
        for day in days:
            available_fach = sum(1 for emp in employees 
                               if emp["qualifikation"] in ("HF", "Leitung")
                               and not is_absent_on_day(emp["id"], day))
            available_total = sum(1 for emp in employees 
                                if not is_absent_on_day(emp["id"], day))
            logging.warning(f"Day {day}:")
            logging.warning(f"  Available Fachpersonen: {available_fach} (Need 0-1)")
            logging.warning(f"  Total available staff: {available_total} (Need at least 3)")

    solution = None
    if model.getModelStatus() == HighsModelStatus.kOptimal:
        solution = model.getSolution()
        logging.info("Solution found!")
        print_shift_plan(solution, variable_names, year, month, days, absences, employee_qualifications)
    else:
        logging.warning(f"Solver failed with status: {model.getModelStatus()}")

    return solution

def print_shift_plan(solution, variable_names, year, month, days, absences, employee_qualifications):
    """Pretty prints the shift plan in a table format with qualifications and totals."""
    if not solution:
        print("No solution found!")
        return

    # Create a dictionary to store shifts by date and employee
    shift_plan = {}
    col_value = solution.col_value
    
    # Process solution into shift_plan dictionary
    for var_index, var_name in enumerate(variable_names):
        if len(var_name) == 3 and col_value[var_index] > 0.9:
            employee_id, day, shift_code = var_name
            day_str = f"{day.zfill(2)}.{month}.{year}"
            
            if day_str not in shift_plan:
                shift_plan[day_str] = {}
            shift_plan[day_str][employee_id] = shift_code

    # Add predefined .w absences
    for employee_id, absence_list in absences.items():
        for absence_day_str, absence_type in absence_list:
            if absence_type == ".w":
                day = absence_day_str.split(".")[0]
                day_str = f"{day.zfill(2)}.{month}.{year}"
                if day_str not in shift_plan:
                    shift_plan[day_str] = {}
                shift_plan[day_str][employee_id] = ".w"

    # Print the header
    print(f"\nShift Plan for {calendar.month_name[month]} {year}\n")
    
    # Column widths
    emp_width = 8  # Width for employee ID
    qual_width = 12  # Width for qualification
    pensum_width = 8  # Width for pensum
    shift_width = 4  # Width for shift codes
    total_width = 3  # Width for totals

    # Define shift categories
    early_shifts = ["B Dienst", "C Dienst"]
    late_shifts = ["VS Dienst", "S Dienst"]
    split_shifts = ["BS Dienst", "C4 Dienst"]

    # Print column headers (dates)
    print(f"{'Employee':>{emp_width}} {'Qual':>{qual_width}} {'Pensum':>{pensum_width}} |", end=" ")
    for day in days:
        print(f"{day:>{shift_width}} |", end=" ")
    print(f"{'F':>{total_width}} | {'S':>{total_width}} | {'SP':>{total_width}} |")
    
    # Print separator
    header_width = emp_width + qual_width + pensum_width + 3  # +3 for spacing and separator
    day_width = (shift_width + 3) * len(days)  # +3 for spacing and separator
    totals_width = (total_width + 3) * 3 + 1  # +3 for spacing and separator, +1 for final |
    print("-" * (header_width + day_width + totals_width))

    # Order employees by qualification
    qual_order = {"Leitung": 0, "HF": 1, "PH": 2, "Ausbildung": 3}
    employee_ids = sorted(set(emp_id for day_shifts in shift_plan.values() for emp_id in day_shifts.keys()),
                        key=lambda x: qual_order.get(employee_qualifications.get(x, ""), 999))

    # Print each employee's schedule with totals
    for emp_id in employee_ids:
        # Count shifts for this employee
        early_count = 0
        late_count = 0
        split_count = 0
        
        # Print employee ID, qualification, and pensum
        qual = employee_qualifications.get(emp_id, "")
        pensum = "100%"  # You'll need to get this from your data
        print(f"{emp_id:>{emp_width}} {qual:>{qual_width}} {pensum:>{pensum_width}} |", end=" ")
        
        for day in days:
            day_str = f"{day.zfill(2)}.{month}.{year}"
            shift_code = shift_plan.get(day_str, {}).get(emp_id, "x")  # Default to "x" if no shift
            print(f"{shift_code:>{shift_width}} |", end=" ")
            
            # Count shift types
            if shift_code in early_shifts:
                early_count += 1
            elif shift_code in late_shifts:
                late_count += 1
            elif shift_code in split_shifts:
                early_count += 1  # Count split shifts for both
                late_count += 1
                split_count += 1
        
        # Print employee totals
        print(f"{early_count:>{total_width}} | {late_count:>{total_width}} | {split_count:>{total_width}} |")

    # Print separator
    print("-" * (header_width + day_width + totals_width))

    # Print daily totals
    print(f"{'Daily Totals':>{emp_width + qual_width + pensum_width}} |", end=" ")
    for day in days:
        day_str = f"{day.zfill(2)}.{month}.{year}"
        day_shifts = shift_plan.get(day_str, {})
        
        # Count shifts for this day
        early_count = sum(1 for shift in day_shifts.values() if shift in early_shifts)
        early_count += sum(1 for shift in day_shifts.values() if shift in split_shifts)  # Add split shifts
        late_count = sum(1 for shift in day_shifts.values() if shift in late_shifts)
        late_count += sum(1 for shift in day_shifts.values() if shift in split_shifts)  # Add split shifts
        split_count = sum(1 for shift in day_shifts.values() if shift in split_shifts)
        
        total = f"{early_count}/{late_count}/{split_count}"
        print(f"{total:>{shift_width}} |", end=" ")
    print()

