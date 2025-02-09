# database.py
import sqlite3
import pandas as pd

DATABASE_NAME = "dienstplan.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row  # Important for accessing columns by name
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            pensum INTEGER,
            diensttage INTEGER,
            qualifikation TEXT,
            SL TEXT,
            Fe TEXT,
            UW TEXT,
            w TEXT
        );
    """)
    #Shifts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT
        )
    """)
    # Pre-populate shifts (This part remains the same)
    shifts_data = [
        ("B Dienst", "6:45 - 16:00"),
        ("C Dienst", "7:30 - 16:45"),
        ("VS Dienst", "11:00 - 20:15"),
        ("S Dienst", "12:00 - 21:15"),
        ("BS Dienst", "6:45 - 11:00 and 17:00 - 21:15"),
        ("C4 Dienst", "7:30 - 12:30 and 16:45 - 20:09"),
        ("Bü Dienst", "Office Work (for Leitung)"),
        ("w", "Wunschfrei"),
        ("x", "Frei"),
        ("Fe", "Ferien"),
        ("IW", "Weiterbildung"),  # Keep IW for consistency, even if not in the input
        ("SL", "Schule"),
        ("uw", "Unbezahlte Schule"),
        ("Kr", "Krankheit"),
    ]
    for code, description in shifts_data:
        try:
            cursor.execute("INSERT INTO shifts (code, description) VALUES (?, ?)", (code, description))
        except sqlite3.IntegrityError:
            pass  # Shift already exists
    #Schedule
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            shift_id TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (shift_id) REFERENCES shifts (code)
        )
    """)

    conn.commit()
    conn.close()

def store_employee_data(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Truncate the table (remove all rows, but keep the table structure)
    cursor.execute("DELETE FROM employees")

    # 2. Drop the old 'fortbildungen' column if it exists in the DataFrame
    if 'fortbildungen' in df.columns:
        df = df.drop(columns=['fortbildungen'])

    # 3. Insert the new data
    df.to_sql('employees', conn, if_exists='append', index=False)

    conn.commit()  # Important: Commit the changes!
    conn.close()

def get_all_employees():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees")
    employees = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return employees

def get_all_shifts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shifts")
    shifts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return shifts

def add_shift_assignment(date, employee_id, shift_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schedule (date, employee_id, shift_id) VALUES (?, ?, ?)", (date, employee_id, shift_id))
    conn.commit()
    conn.close()

def get_schedule():
    conn = get_db_connection()
    query = "SELECT * FROM schedule"
    schedule_df = pd.read_sql_query(query, conn)
    conn.close()
    return schedule_df

def get_employee_name(employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM employees WHERE id = ?", (employee_id,))
    result = cursor.fetchone()
    conn.close()
    return result['name'] if result else 'Unknown'

def get_employee_qualifications():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, qualifikation FROM employees")
    qualifications = {row['id']: row['qualifikation'] for row in cursor.fetchall()}
    conn.close()
    return qualifications

def get_employee_workload():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, `diensttage` FROM employees")
    workloads = {row['id']: row['diensttage'] for row in cursor.fetchall()}
    conn.close()
    return workloads
    
def get_employee_absences():
    """Returns a dictionary mapping employee IDs to a list of their absences."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, SL, Fe, UW, w FROM employees")
    absences = {}
    for row in cursor.fetchall():
        employee_id = row['id']
        absence_list = []

        # Helper function to process comma-separated dates
        def process_dates(date_string):
            if date_string:
                return [d.strip() for d in date_string.split(',') if d.strip()]
            return []

        # Process SL (Schule)
        for date in process_dates(row['SL']):
            absence_list.append((date, "SL"))

        # Process UW (Unbezahlte Weiterbildung)
        for date in process_dates(row['UW']):
            absence_list.append((date, "uw"))
        
        #Process Wunschfrei
        for date in process_dates(row['w']):
            absence_list.append((date, "w"))

        # Process Fe (Ferien) - Handle date ranges
        if row['Fe']:
            ferien_ranges = [r.strip() for r in row['Fe'].split(',') if r.strip()]
            for ferien_range in ferien_ranges:
                try:
                    if '-' in ferien_range:  # It's a range
                        start_date_str, end_date_str = ferien_range.split('-')
                        start_day, start_month = map(int, start_date_str.split('.'))
                        end_day, end_month = map(int, end_date_str.split('.'))

                        if start_month == end_month:
                            for day in range(start_day, end_day + 1):
                                absence_list.append((f"{day}.{start_month}.", "Fe"))
                        else:
                            # For simplicity, assume it only spans one month
                            for day in range(start_day, 32):
                                absence_list.append((f"{day}.{start_month}.", "Fe"))
                            for day in range(1, end_day + 1):
                                absence_list.append((f"{day}.{end_month}.", "Fe"))
                    else:  # Single date
                        absence_list.append((ferien_range, "Fe"))
                except ValueError:
                    pass #ignore errors

        absences[employee_id] = absence_list
    conn.close()
    return absences