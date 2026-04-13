# نبض الفجيرة - Fujairah Nabd Demo

## نظرة عامة | Overview

**العربية:**
تطبيق تجريبي لنظام نبض الفجيرة لتحليل استفسارات المتعاملين باستخدام الذكاء الاصطناعي. يتيح التطبيق رفع الملفات (Excel أو PDF) ومعالجتها وتحميل التقرير النهائي.

**English:**
A demo application for Fujairah Nabd (نبض) - an AI-powered system for analyzing customer inquiries. The app allows uploading files (Excel or PDF), processing them, and downloading the final report.

---

## 🚀 التشغيل السريع | Quick Start

### خطوة واحدة فقط | Just One Step

**على macOS/Linux:**
```bash
./run.sh
```

**على Windows:**
```cmd
run.bat
```

التطبيق سيفتح تلقائياً في المتصفح على | The app will automatically open at:
```
http://localhost:8501
```

### التشغيل اليدوي | Manual Run

```bash
# تثبيت المكتبات | Install dependencies
pip install -r requirements.txt

# تشغيل التطبيق | Run the app
streamlit run app.py
```

---

## ✨ المميزات | Features

- ✅ **واجهة عربية 100%** - Full Arabic interface with complete RTL support
- 📤 **رفع الملفات** - Upload Excel (.xlsx, .xls) and PDF files
- ⏱️ **معالجة ذكية** - 2-minute processing simulation with 4 stages
- 📥 **تحميل التقرير** - Download comprehensive Word report
- 🎨 **تصميم احترافي** - Modern design with Fujairah brand colors
- 🔒 **آمن** - All data stays local, no external servers

### مراحل المعالجة | Processing Stages

1. **جاري رفع الملفات** (0-25%) - File upload and validation
2. **تحليل البيانات** (25-50%) - Data analysis and extraction
3. **معالجة الاستفسارات** (50-75%) - AI-powered inquiry processing
4. **إنشاء التقرير النهائي** (75-100%) - Report generation

---

## 📋 المتطلبات | Requirements

- Python 3.8 أو أحدث | Python 3.8 or higher
- pip (مدير المكتبات) | pip (package manager)
- متصفح حديث | Modern browser

---

## 📁 هيكل المشروع | Project Structure

```
sim-fujairah-inquiries-ai/
├── app.py                      # التطبيق الرئيسي
├── requirements.txt            # المكتبات المطلوبة
├── README.md                   # هذا الملف
├── run.sh / run.bat           # سكريبت التشغيل
├── .streamlit/
│   └── config.toml            # إعدادات Streamlit
├── assets/                    # الشعارات والصور
├── inquiries-output/          # تقارير استفسارات المتعاملين
└── complaints-output/         # تقارير شكاوى المتعاملين
```

---

## 🎬 كيفية الاستخدام | How to Use

1. **افتح التطبيق** - Run `./run.sh` or `run.bat`
2. **ارفع ملف** - Upload Excel or PDF file
3. **ابدأ التحليل** - Click "بدء التحليل" and wait 2 minutes
4. **حمّل التقرير** - Download the generated Word report

---

## 🌐 النشر | Deployment

### على Streamlit Cloud

```bash
# رفع الكود إلى GitHub
git init
git add .
git commit -m "Initial commit"
git push -u origin main

# ثم انتقل إلى https://streamlit.io/cloud
# واختر المستودع وملف app.py
```

### باستخدام Docker

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t fujairah-nabd-demo .
docker run -p 8501:8501 fujairah-nabd-demo
```

---

## 🐛 استكشاف الأخطاء | Troubleshooting

### "Port already in use"
```bash
streamlit run app.py --server.port 8502
```

### الخطوط العربية لا تظهر
- تحقق من اتصال الإنترنت (الخطوط تُحمل من Google Fonts)
- امسح ذاكرة المتصفح المؤقتة

### الملف لا يتم تحميله
```bash
ls -la inquiries-output/
ls -la complaints-output/
chmod 644 inquiries-output/*.docx
chmod 644 complaints-output/*.docx
```

---

## 📝 ملاحظات مهمة | Important Notes

⚠️ **هذا تطبيق تجريبي** - لا يتم إجراء معالجة حقيقية للبيانات  
⚠️ **This is a demo app** - No actual data processing is performed

✅ التقرير المُنتج هو نموذج ثابت لأغراض العرض  
✅ The generated report is a static sample for demonstration purposes

🔒 جميع الملفات المرفوعة تبقى محلية ولا يتم إرسالها إلى أي خادم  
🔒 All uploaded files remain local and are not sent to any server

---

## 📞 الدعم | Support

- [Streamlit Documentation](https://docs.streamlit.io)
- [Python Documentation](https://docs.python.org)

---

**تم التطوير بواسطة | Developed for:** حكومة الفجيرة | Fujairah Government  
**التاريخ | Date:** أبريل 2026 | April 2026  
**الإصدار | Version:** 1.0.0
