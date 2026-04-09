@echo off
REM Fujairah Nabd Demo - Run Script (Windows)
REM نبض الفجيرة - سكريبت التشغيل (ويندوز)

echo ================================================
echo نبض الفجيرة - Fujairah Nabd Demo
echo ================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8 or higher.
    echo ❌ Python غير مثبت. يرجى تثبيت Python 3.8 أو أحدث.
    pause
    exit /b 1
)

echo ✅ Python found
python --version
echo.

REM Check if pip is installed
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip is not installed. Please install pip.
    echo ❌ pip غير مثبت. يرجى تثبيت pip.
    pause
    exit /b 1
)

echo ✅ pip found
echo.

REM Check if requirements.txt exists
if not exist "requirements.txt" (
    echo ❌ requirements.txt not found!
    echo ❌ ملف requirements.txt غير موجود!
    pause
    exit /b 1
)

REM Install dependencies
echo 📦 Installing dependencies...
echo 📦 جاري تثبيت المكتبات المطلوبة...
echo.

pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ❌ Failed to install dependencies
    echo ❌ فشل تثبيت المكتبات المطلوبة
    pause
    exit /b 1
)

echo.
echo ✅ Dependencies installed successfully
echo ✅ تم تثبيت المكتبات بنجاح
echo.

REM Check if app.py exists
if not exist "app.py" (
    echo ❌ app.py not found!
    echo ❌ ملف app.py غير موجود!
    pause
    exit /b 1
)

REM Run the app
echo 🚀 Starting Fujairah Nabd Demo...
echo 🚀 جاري تشغيل تطبيق نبض الفجيرة...
echo.
echo The app will open automatically in your browser
echo سيفتح التطبيق تلقائياً في المتصفح
echo.
echo URL: http://localhost:8501
echo.
echo Press Ctrl+C to stop the application
echo اضغط Ctrl+C لإيقاف التطبيق
echo.
echo ================================================
echo.

streamlit run app.py
