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
    
    def process_date_entries(date_string, absence_type):
        if not date_string:
            return []
        
        result = []
        entries = [e.strip() for e in date_string.split(',') if e.strip()]
        
        for entry in entries:
            try:
                if '-' in entry or '–' in entry:  # Handle both hyphen types
                    parts = entry.split('-') if '-' in entry else entry.split('–')
                    start_date_str, end_date_str = [p.strip() for p in parts]
                    
                    start_day = int(start_date_str.split('.')[0])
                    start_month = int(start_date_str.split('.')[1])
                    end_day = int(end_date_str.split('.')[0])
                    end_month = int(end_date_str.split('.')[1])
                    
                    if start_month == end_month:
                        for day in range(start_day, end_day + 1):
                            result.append((f"{day:02d}.{start_month:02d}.", absence_type))
                    else:
                        for day in range(start_day, 32):
                            result.append((f"{day:02d}.{start_month:02d}.", absence_type))
                        for day in range(1, end_day + 1):
                            result.append((f"{day:02d}.{end_month:02d}.", absence_type))
                else:
                    day = int(entry.split('.')[0])
                    month = int(entry.split('.')[1])
                    result.append((f"{day:02d}.{month:02d}.", absence_type))
            except (ValueError, IndexError) as e:
                print(f"Warning: Invalid date format in {entry}: {e}")
                continue
        
        return result

    for row in cursor.fetchall():
        employee_id = row['id']  # Keep as integer
        absence_list = []
        
        # All these are treated as absences - days where employee cannot be scheduled
        if row['SL']:
            absence_list.extend(process_date_entries(row['SL'], "SL"))
        if row['Fe']:
            absence_list.extend(process_date_entries(row['Fe'], "Fe"))
        if row['UW']:
            absence_list.extend(process_date_entries(row['UW'], "uw"))
        if row['w']:
            absence_list.extend(process_date_entries(row['w'], "w"))  # Just 'w', not '.w'
        
        if absence_list:  # Only add if there are absences
            absences[employee_id] = absence_list

    conn.close()
    return absences

def get_employee_pensum(employee_id):
    """Get the pensum for an employee."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pensum FROM employees WHERE id = ?", (employee_id,))
    result = cursor.fetchone()
    conn.close()
    return f"{result[0]}%" if result else "100%"

def get_employee_qualification(employee_id):
    """Get the qualification for an employee."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT qualifikation FROM employees WHERE id = ?", (employee_id,))
    result = cursor.fetchone()
    conn.close()
    return result['qualifikation'] if result else 'Unknown'