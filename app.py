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
        data.append({"date": date_str, "employee_id": employee_id, "employee_name": employee_name, "shift_id": shift_id})
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
    ch_holidays = holidays.CH(years=year, prov="BS")

    # --- Main Area: Schedule Creation ---
    st.header(f"3. Create Schedule ({calendar.month_name[month]} {year})")
    num_days = calendar.monthrange(year, month)[1]
    dates = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]
    employees = database.get_all_employees()
    shifts = database.get_all_shifts()

    # --- Automatic Schedule Generation and Solution Selection ---
    if st.button("Generate Schedule"):
        try:
            absences = database.get_employee_absences()
            employee_qualifications = database.get_employee_qualifications()
            employee_workload = database.get_employee_workload()
            # Get ALL solutions
            solutions = scheduler.generate_schedule(
                employees, shifts, absences, employee_qualifications, employee_workload, year, month, ch_holidays
            )

            if solutions:
                st.session_state.solutions = solutions  # Store solutions in session state
                st.session_state.selected_solution_index = 0  # Initialize selection
                st.success(f"Found {len(solutions)} solutions!")
            else:
                st.error("No solution found.  Check constraints and employee availability.")
        except Exception as e:
            st.error(f"Error generating schedule: {e}")
            logging.exception("Error generating schedule")

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

        # Create pivot table for display
        pivot_schedule = pd.pivot_table(
            solution_df,
            index="employee_name",
            columns="date",
            values="shift_id",
            aggfunc="first",
        )
        st.dataframe(pivot_schedule)
    
        # --- Save Selected Solution to Database ---
        #Clear schedule
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedule")
        conn.commit()
        conn.close()
        #Save selected Solution
        for index, row in solution_df.iterrows():
            if row["shift_id"] is not None: #Only add if a shift is assigned
                try:
                    database.add_shift_assignment(row["date"], row["employee_id"], row["shift_id"])
                except Exception as e:
                    logging.error(f"Failed to add shift assignment: {e}")

        # --- Export Selected Solution to Excel ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pivot_schedule.to_excel(writer, sheet_name='Schedule')
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
            "Select Shift", [shift["code"] for shift in shifts]
        )  # Display only shift codes.

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