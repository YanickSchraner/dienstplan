# utils.py
import pandas as pd

def read_employee_data(uploaded_file):
    """Reads employee data from an Excel file, handling SL, Fe, and UW."""
    try:
        df = pd.read_excel(uploaded_file)
        # Basic validation and cleaning
        df = df.dropna(how='all')
        df.columns = [col.strip() for col in df.columns]

        # Ensure the expected columns exist, filling with empty strings if missing
        for col in ['SL', 'Fe', 'UW']:
            if col not in df.columns:
                df[col] = ''

        return df
    except Exception as e:
        raise ValueError(f"Error reading Excel file: {e}")