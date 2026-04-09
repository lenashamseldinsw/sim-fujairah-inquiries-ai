#!/bin/bash

# Fujairah Nabd Demo - Run Script
# نبض الفجيرة - سكريبت التشغيل

echo "================================================"
echo "نبض الفجيرة - Fujairah Nabd Demo"
echo "================================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    echo "❌ Python 3 غير مثبت. يرجى تثبيت Python 3.8 أو أحدث."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
echo ""

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    echo "❌ pip3 غير مثبت. يرجى تثبيت pip."
    exit 1
fi

echo "✅ pip found"
echo ""

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found!"
    echo "❌ ملف requirements.txt غير موجود!"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
echo "📦 جاري تثبيت المكتبات المطلوبة..."
echo ""

pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to install dependencies"
    echo "❌ فشل تثبيت المكتبات المطلوبة"
    exit 1
fi

echo ""
echo "✅ Dependencies installed successfully"
echo "✅ تم تثبيت المكتبات بنجاح"
echo ""

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo "❌ app.py not found!"
    echo "❌ ملف app.py غير موجود!"
    exit 1
fi

# Run the app
echo "🚀 Starting Fujairah Nabd Demo..."
echo "🚀 جاري تشغيل تطبيق نبض الفجيرة..."
echo ""
echo "The app will open automatically in your browser"
echo "سيفتح التطبيق تلقائياً في المتصفح"
echo ""
echo "URL: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the application"
echo "اضغط Ctrl+C لإيقاف التطبيق"
echo ""
echo "================================================"
echo ""

streamlit run app.py
