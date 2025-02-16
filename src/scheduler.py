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
          # --- Updated constraint below ---
          solver.Add( Z >= sum(sum(x[(e_id, j, s)] for s in required_shifts.keys()) for j in range(d, d+5)) - 4 )
          if d + 5 <= num_days:
               slack1 = solver.NumVar(0, 1, f"{e_id}_consec_slack1_{d}")
               solver.Add( sum(x[(e_id, d+5, s)] for s in required_shifts.keys()) <= 1 - Z + slack1 )
               consec_slacks.append(slack1)
          if d + 6 <= num_days:
               slack2 = solver.NumVar(0, 1, f"{e_id}_consec_slack2_{d}")
               solver.Add( sum(x[(e_id, d+6, s)] for s in required_shifts.keys()) <= 1 - Z + slack2 )
               consec_slacks.append(slack2)

# Lehrling Constraints:
# For Lehrlinge with qualification "Ausbildung 1" or "Ausbildung 2":
#   - They are allowed to work only on weekdays.
#   - They can only be assigned to "B Dienst" or "C Dienst".
for d in range(1, num_days + 1):
     current_date = datetime.date(year, month, d)
     for emp in employees:
          e_id = emp["id"]
          if employee_qualifications.get(e_id) in {"Ausbildung 1", "Ausbildung 2"}:
               # Force no assignments on weekends.
               if current_date.weekday() >= 5:
                    solver.Add(sum(x[(e_id, d, s)] for s in required_shifts.keys()) == 0)
               else:
                    # On weekdays, force shifts other than "B Dienst" or "C Dienst" to 0.
                    for shift_code in required_shifts.keys():
                         if shift_code not in {"B Dienst", "C Dienst"}:
                              solver.Add(x[(e_id, d, shift_code)] == 0)

# Global variable used by app.py to extract the solution.
variable_names = []

## Define lists to collect slack variables for soft constraints
consec_slacks = []
late_slacks_total = []
late_slacks_qual = []
extra_split_list = []

## Define penalty parameters for soft constraints
penalty_consecutive = 50
penalty_late = 100
penalty_split_extra = 20

# Late group coverage and fachkraft constraint
for d in range(1, num_days + 1):
     slack_late_total = solver.NumVar(0, 3, f"slack_late_total_{d}")
     solver.Add(sum(x[(emp["id"], d, s)] for s in late_shifts for emp in employees) + slack_late_total >= 3)  # late group coverage (soft)
     late_slacks_total.append(slack_late_total)

     slack_late_qual = solver.NumVar(0, 1, f"slack_late_qual_{d}")
     solver.Add(
         (sum(x[(emp["id"], d, "S Dienst")] for emp in employees if employee_qualifications.get(emp["id"]) in fach_qual)
          +
          sum(x[(emp["id"], d, s)] for s in {"BS Dienst", "C4 Dienst"}
              for emp in employees if employee_qualifications.get(emp["id"]) in fach_qual))
         + slack_late_qual
         >= 1
     )
     late_slacks_qual.append(slack_late_qual)

for d in range(1, num_days + 1):
     total_split = sum(x[(emp["id"], d, "BS Dienst")] + x[(emp["id"], d, "C4 Dienst")] for emp in employees)
     extra_split = solver.NumVar(0, solver.infinity(), f"extra_split_{d}")
     solver.Add(extra_split >= total_split - 3)
     extra_split_list.append(extra_split)

# Set objective: minimize penalties for soft constraints
objective = solver.Objective()
for slack in consec_slacks:
     objective.SetCoefficient(slack, penalty_consecutive)
for slack in late_slacks_total:
     objective.SetCoefficient(slack, penalty_late)
for slack in late_slacks_qual:
     objective.SetCoefficient(slack, penalty_late)
for extra in extra_split_list:
     objective.SetCoefficient(extra, penalty_split_extra)
objective.SetMinimization() 