import streamlit.web.cli as stcli
import sys
import os
import webbrowser
import time

def fix_path():
    # Get the directory where the executable is located
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle
        application_path = sys._MEIPASS
    else:
        # If the application is run from a Python interpreter
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    # Change to the application directory
    os.chdir(application_path)
    return application_path

def main():
    app_path = fix_path()
    # Configure Streamlit to run in production mode
    os.environ['STREAMLIT_SERVER_PORT'] = '8501'
    os.environ['STREAMLIT_SERVER_ADDRESS'] = 'localhost'
    os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
    os.environ['STREAMLIT_GLOBAL_DEVELOPMENT_MODE'] = 'false'
    
    # Open the browser after a short delay
    webbrowser.open('http://localhost:8501', new=2)
    
    # Run the Streamlit application
    sys.argv = ["streamlit", "run", "app.py"]
    sys.exit(stcli.main())

if __name__ == '__main__':
    main() 