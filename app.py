import streamlit as st
import pandas as pd
import database
import utils
import calendar
import scheduler
import holidays
from datetime import date
import io
import logging

def solution_to_dataframe(solution, employees, year, month):
    """Converts a solution dictionary to a Pandas DataFrame."""
    data = []
    for (employee_id, day_str), shift_id in solution.items():
        date_str = f"{year}-{month:02d}-{int(day_str):02d}"
        employee_name = database.get_employee_name(employee_id)
        employee_qual = database.get_employee_qualification(employee_id)
        employee_pensum = database.get_employee_pensum(employee_id)
        data.append({
            "date": date_str,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "qualification": employee_qual,
            "pensum": employee_pensum,
            "shift_id": shift_id
        })
    return pd.DataFrame(data)

def main():
    st.title("Automated Shift Scheduler")
    database.create_tables()

    # --- Sidebar: File Upload ---
    st.sidebar.header("1. Upload Employee Data")
    uploaded_file = st.sidebar.file_uploader("Choose an Excel file", type="xlsx")

    if uploaded_file is not None:
        try:
            employee_df = utils.read_employee_data(uploaded_file)
            database.store_employee_data(employee_df)
            st.sidebar.success("Employee data imported successfully!")
        except Exception as e:

            st.sidebar.error(f"Error processing the file: {e}")

    # --- Sidebar: Show Employees (Optional) ---
    if st.sidebar.checkbox("Show Employees"):
        st.header("Employee Data")
        try:
            employees = database.get_all_employees()
            if employees:
                st.dataframe(pd.DataFrame(employees))
            else:
                st.write("No employee data found.")
        except Exception as e:
            st.error(f"Error retrieving employee data: {e}")

    # --- Main Area: Date Selection ---
    st.header("2. Select Month and Year")
    today = date.today()
    selected_date = st.date_input(
        "Select a month",
        today,
        min_value=date(2020, 1, 1),
        max_value=date(2030, 12, 31),
        format="DD/MM/YYYY",
    )
    year = selected_date.year
    month = selected_date.month
    # --- Get Holidays for Basel-Stadt ---
    ch_holidays = holidays.Switzerland(years=year, prov="BS")

    # --- Main Area: Schedule Creation ---
    st.header(f"3. Create Schedule ({calendar.month_name[month]} {year})")
    num_days = calendar.monthrange(year, month)[1]
    dates = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    employees = database.get_all_employees()
    shifts = database.get_all_shifts()
    logging.info(f"Shifts type: {type(shifts)}")
    logging.info(f"First shift type: {type(shifts[0]) if shifts else 'No shifts'}")
    logging.info(f"Shifts: {shifts}")

    # --- Automatic Schedule Generation and Solution Selection ---
    if st.button("Generate Schedule"):
        try:
            absences = database.get_employee_absences()
            
            employee_qualifications = database.get_employee_qualifications()
            
            employee_workload = database.get_employee_workload()
            
            solution = scheduler.generate_schedule_highs(
                employees,
                shifts,
                absences,
                employee_qualifications,
                employee_workload,
                year,
                month,
                ch_holidays
            )
            
            if solution:
                # Convert HiGHS solution to schedule format
                schedule = {}
                col_value = solution.col_value
                
                for var_index, var_name in enumerate(scheduler.variable_names):
                    if len(var_name) == 3 and col_value[var_index] > 0.9:
                        employee_id, day, shift_code = var_name
                        day_str = f"{year}-{month:02d}-{int(day):02d}"
                        schedule[(employee_id, day)] = shift_code

                st.session_state.solutions = [schedule]  # Store as list for compatibility
                st.session_state.selected_solution_index = 0
                st.success("Solution found!")
            else:
                st.error("No feasible solution found. Check staffing levels and constraints.")
        except Exception as e:
            st.error(f"Error generating schedule: {str(e)}")
            logging.exception("Detailed error in schedule generation:")

    # --- Solution Selection (Dropdown) ---
    if "solutions" in st.session_state and st.session_state.solutions:
        selected_index = st.selectbox(
            "Select Solution",
            options=range(1, len(st.session_state.solutions) + 1),
            index=st.session_state.selected_solution_index,  # Use stored index
            format_func=lambda x: f"Solution {x}",  # Display "Solution 1", "Solution 2", etc.
        )
        # Update the selected index in session state
        st.session_state.selected_solution_index = selected_index -1

        # --- Display Selected Solution ---
        selected_solution = st.session_state.solutions[st.session_state.selected_solution_index]
        solution_df = solution_to_dataframe(selected_solution, employees, year, month)

        # Get absences for the selected month
        absences = database.get_employee_absences()
        absence_data = []
        for emp_id, dates in absences.items():
            employee_name = database.get_employee_name(emp_id)
            employee_qual = database.get_employee_qualification(emp_id)
            employee_pensum = database.get_employee_pensum(emp_id)
            for absence in dates:
                day_month = absence[0]  # Format: "DD.MM."
                absence_type = absence[1]
                
                # Convert date format
                day = int(day_month.split('.')[0])
                # Only process if it's for the selected month
                if f"{month:02d}." in day_month:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    absence_data.append({
                        "date": date_str,
                        "employee_id": emp_id,
                        "employee_name": employee_name,
                        "qualification": employee_qual,
                        "pensum": employee_pensum,
                        "shift_id": absence_type
                    })
        
        # Combine solution and absence DataFrames
        absence_df = pd.DataFrame(absence_data) if absence_data else pd.DataFrame()
        if not absence_df.empty:
            combined_df = pd.concat([solution_df, absence_df])
        else:
            combined_df = solution_df

        # Create pivot table for display
        pivot_schedule = pd.pivot_table(
            combined_df,
            index=["qualification", "employee_name", "pensum"],
            columns="date",
            values="shift_id",
            aggfunc="first",
        ).fillna('x')  # Fill empty cells with 'x'
        
        # Reset index to manipulate columns
        pivot_schedule = pivot_schedule.reset_index()
        
        # Add total workdays column
        pivot_schedule['Soll'] = pivot_schedule['employee_name'].apply(
            lambda x: database.get_employee_diensttage(
                next(emp['id'] for emp in employees if emp['name'] == x)
            )
        )
        
        # Calculate actual workdays (shifts + Fe + SL)
        def count_workdays(row):
            # Get all date columns (they start with the year)
            date_cols = [col for col in row.index if isinstance(col, str) and col.startswith(str(year))]
            count = 0
            for col in date_cols:
                value = row[col]
                if isinstance(value, str) and value not in ['x', 'w', 'uw']:  # Count everything except 'x', 'w', and 'uw'
                    count += 1
            return count
            
        pivot_schedule['Ist'] = pivot_schedule.apply(count_workdays, axis=1)
        
        # Sort by qualification in custom order
        qual_order = {"Leitung": 0, "HF": 1, "PH": 2, "Ausbildung": 3}
        pivot_schedule['qual_order'] = pivot_schedule['qualification'].map(qual_order)
        pivot_schedule = pivot_schedule.sort_values('qual_order')
        
        # Drop qual_order first
        pivot_schedule = pivot_schedule.drop('qual_order', axis=1)
        
        # Then reorder columns
        cols = ['qualification', 'employee_name', 'pensum', 'Soll', 'Ist']
        date_cols = [col for col in pivot_schedule.columns if isinstance(col, str) and col.startswith(str(year))]
        pivot_schedule = pivot_schedule[cols + date_cols]
        
        # Set final index
        pivot_schedule = pivot_schedule.set_index(['qualification', 'employee_name', 'pensum'])
        
        # Calculate daily totals
        early_shifts = ["B Dienst", "C Dienst"]
        late_shifts = ["VS Dienst", "S Dienst"]
        split_shifts = ["BS Dienst", "C4 Dienst"]
        
        daily_totals = pd.DataFrame(index=pd.Index(['Early/Late/Split'], name='Totals'))
        for col in pivot_schedule.columns:
            shifts = pivot_schedule[col].dropna()
            # Count regular shifts
            early_count = sum(1 for s in shifts if s in early_shifts)
            late_count = sum(1 for s in shifts if s in late_shifts)
            split_count = sum(1 for s in shifts if s in split_shifts)
            
            daily_totals[col] = f"{early_count}/{late_count}/{split_count}"
        
        # Display the schedule with totals
        st.dataframe(pivot_schedule)
        st.dataframe(daily_totals)
        
        # Export to Excel with formatting
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter', mode='wb') as writer:
            pivot_schedule.to_excel(writer, sheet_name='Schedule')
            daily_totals.to_excel(writer, sheet_name='Schedule', startrow=len(pivot_schedule)+2)
            
            # Get the xlsxwriter workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['Schedule']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'border': 1
            })
            
            # Write headers with formatting
            for col_num, value in enumerate(pivot_schedule.columns.values):
                worksheet.write(0, col_num + 3, value, header_format)
            
            # Adjust column widths
            worksheet.set_column('A:A', 12)  # Qualification
            worksheet.set_column('B:B', 20)  # Name
            worksheet.set_column('C:C', 8)   # Pensum
            worksheet.set_column('D:AE', 6)  # Dates
            
        excel_data = output.getvalue()
        st.download_button(
            label="Export Selected Solution to Excel",
            data=excel_data,
            file_name=f"schedule_{year}-{month:02d}_solution_{selected_index}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # --- Manual Schedule Creation (Keep this, but it should be used *after* automatic generation)---
    with st.form(key="schedule_form"):
        selected_date = st.selectbox("Select Date", dates)
        selected_employee_id = st.selectbox(
            "Select Employee", [f"{emp['id']} - {emp['name']}" for emp in employees]
        )
        selected_shift_id = st.selectbox(
            "Select Shift", [shift["code"] for shift in shifts if isinstance(shift, dict)]
        )

        submit_button = st.form_submit_button(label="Add to Schedule")
        if submit_button:
            try:
                # Extract the numeric employee ID
                employee_id = int(selected_employee_id.split(" - ")[0])
                database.add_shift_assignment(selected_date, employee_id, selected_shift_id)
                st.success(
                    f"Shift assigned: {selected_employee_id} on {selected_date} for {selected_shift_id}"
                )
                #  After a manual add, clear the solutions to avoid confusion
                if "solutions" in st.session_state:
                    del st.session_state["solutions"]

            except Exception as e:
                st.error(f"Error adding shift: {e}")
                logging.exception("Error adding shift manually")

if __name__ == "__main__":
    main()