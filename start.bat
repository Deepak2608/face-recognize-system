@echo off
REM Quick Start Script for Face Recognition Web App (Windows)

echo.
echo ====================================================
echo   FACE RECOGNITION WEB APP - QUICK START
echo ====================================================
echo.

REM Check if venv exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created!
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo.
echo Installing packages (this may take a few minutes)...
pip install -r requirements_web.txt

REM Run the app
echo.
echo ====================================================
echo   STARTING APPLICATION...
echo ====================================================
echo.
echo Open your browser and go to:
echo   http://localhost:5000
echo.
echo Press Ctrl+C to stop the app
echo ====================================================
echo.

python app.py

pause
