import PyInstaller.__main__
import os
import shutil

def build_exe():
    # Define the name of your application
    app_name = "Dienstplan"
    
    # Create a directory for the build if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')
    
    # Copy necessary data files
    data_files = [
        ('employees.csv', '.'),
        ('employees.xlsx', '.'),
        ('dienstplan.db', '.')
    ]
    
    # Prepare the data files for PyInstaller
    datas = []
    for src, dst in data_files:
        if os.path.exists(src):
            datas.append((src, dst))
    
    # Convert datas list to PyInstaller format with semicolon for Windows
    datas_args = []
    for src, dst in datas:
        datas_args.extend(['--add-data', f"{src};{dst}"])
    
    # Add app.py to the data files
    datas_args.extend(['--add-data', 'app.py;.'])
    
    # Define PyInstaller arguments
    args = [
        'launcher.py',  # Our new launcher script
        '--name=' + app_name,
        '--onedir',  # Create a directory containing the executable
        '--windowed',  # Hide the console window
        *datas_args,  # Spread the data arguments
        '--hidden-import=streamlit',
        '--hidden-import=streamlit.web.cli',
        '--hidden-import=streamlit.runtime',
        '--hidden-import=streamlit.runtime.scriptrunner',
        '--hidden-import=streamlit.runtime.app_session',
        '--hidden-import=streamlit.server',
        '--hidden-import=streamlit.web',
        '--hidden-import=pandas',
        '--hidden-import=sqlite3',
        '--hidden-import=holidays',
        '--hidden-import=calendar',
        '--hidden-import=openpyxl',
        '--hidden-import=holidays.constants',
        '--hidden-import=holidays.holiday_base',
        '--hidden-import=holidays.utils',
        '--hidden-import=holidays.calendars',
        '--hidden-import=holidays.groups',
        '--hidden-import=holidays.countries',
        '--hidden-import=holidays.countries.germany',
        '--collect-all=streamlit',
        '--collect-all=altair',
        '--collect-all=pandas',
        '--collect-all=numpy',
        '--collect-all=holidays',
        '--copy-metadata=streamlit',
        '--copy-metadata=altair',
        '--copy-metadata=pandas',
        '--copy-metadata=numpy',
        '--copy-metadata=pyarrow',
        '--copy-metadata=toolz',
        '--copy-metadata=holidays',
        '--copy-metadata=protobuf',
        '--copy-metadata=packaging',
        '--copy-metadata=importlib_metadata',
        '--copy-metadata=click',
        '--copy-metadata=typing_extensions',
    ]
    
    # Run PyInstaller
    PyInstaller.__main__.run(args)
    
    print(f"\nBuild complete! You can find your executable in the 'dist/{app_name}' directory.")
    print("To run the application, copy the entire directory to your USB stick and run the executable.")

if __name__ == "__main__":
    build_exe() 