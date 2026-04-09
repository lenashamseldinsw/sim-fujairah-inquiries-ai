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

### الوظائف الرئيسية | Main Features

- ✅ **واجهة عربية 100%** - Full Arabic interface with complete RTL support
- 📤 **رفع الملفات** - Upload Excel (.xlsx, .xls) and PDF files
- ⏱️ **معالجة ذكية** - 2-minute processing simulation with 4 stages
- 📥 **تحميل التقرير** - Download comprehensive Word report
- 🎨 **تصميم احترافي** - Modern design with Fujairah brand colors (#B68A35)
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
├── app.py                                          # التطبيق الرئيسي (547 lines)
├── requirements.txt                                # المكتبات المطلوبة
├── README.md                                       # هذا الملف
├── DEMO_GUIDE.md                                   # دليل العرض التجريبي
├── run.sh / run.bat                                # سكريبت التشغيل
├── .streamlit/
│   └── config.toml                                 # إعدادات Streamlit
├── assets/
│   └── logo_placeholder.svg                        # الشعار
├── outputs/
│   └── تقرير تحليل استفسارات المتعاملين.docx     # التقرير النموذجي
└── تقرير تحليل استفسارات المتعاملين.docx          # التقرير الأصلي
```

---

## 🎨 التصميم | Design

### الألوان | Colors
- **الأساسي | Primary:** `#B68A35` (ذهبي الفجيرة | Fujairah Gold)
- **الثانوي | Secondary:** `#E5E5E5` (رمادي فاتح | Light Grey)
- **النجاح | Success:** `#28a745` (أخضر | Green)

### الخطوط | Fonts
- **الأساسي | Primary:** Cairo (Google Fonts)
- **الثانوي | Secondary:** Tajawal (Google Fonts)

---

## 🎬 كيفية الاستخدام | How to Use

### 1️⃣ افتح التطبيق | Open the App
```bash
./run.sh  # أو run.bat على Windows
```

### 2️⃣ ارفع ملف | Upload File
- اختر ملف Excel أو PDF
- أو اسحبه وأفلته

### 3️⃣ ابدأ التحليل | Start Analysis
- انقر على "بدء التحليل"
- انتظر دقيقتين

### 4️⃣ حمّل التقرير | Download Report
- انقر على "تحميل التقرير"
- افتح الملف واستعرضه

---

## 🌐 النشر | Deployment

### على Streamlit Cloud (موصى به | Recommended)

1. **رفع الكود | Upload Code:**
```bash
git init
git add .
git commit -m "Initial commit"
git push -u origin main
```

2. **نشر التطبيق | Deploy App:**
- اذهب إلى https://streamlit.io/cloud
- انقر على "New app"
- اختر المستودع والفرع
- حدد `app.py` كملف رئيسي

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
# بناء وتشغيل | Build and run
docker build -t fujairah-nabd-demo .
docker run -p 8501:8501 fujairah-nabd-demo
```

### الوصول من الأجهزة الأخرى | Access from Other Devices

```bash
# اعثر على عنوان IP | Find IP address
ifconfig | grep "inet " | grep -v 127.0.0.1  # macOS/Linux
ipconfig  # Windows

# شغل التطبيق | Run app
streamlit run app.py --server.address 0.0.0.0

# افتح في الجهاز الآخر | Open on other device
# http://<YOUR-IP>:8501
```

---

## 🐛 استكشاف الأخطاء | Troubleshooting

### المشكلة: "Python not found"
```bash
# تثبيت Python | Install Python
# قم بزيارة | Visit: https://www.python.org/downloads/
```

### المشكلة: "Port already in use"
```bash
# استخدم منفذ آخر | Use different port
streamlit run app.py --server.port 8502
```

### المشكلة: الخطوط العربية لا تظهر
- تحقق من اتصال الإنترنت (الخطوط تُحمل من Google Fonts)
- امسح ذاكرة المتصفح المؤقتة
- جرب متصفح آخر

### المشكلة: الملف لا يتم تحميله
```bash
# تحقق من وجود الملف | Check file exists
ls -la outputs/

# تحقق من الأذونات | Check permissions
chmod 644 outputs/*.docx
```

---

## ✅ قائمة الفحص | Testing Checklist

### قبل العرض التجريبي | Pre-Demo Testing

- [ ] تثبيت جميع المكتبات المطلوبة
- [ ] تشغيل التطبيق بنجاح
- [ ] فتح التطبيق في المتصفح
- [ ] اختبار رفع ملف Excel
- [ ] اختبار رفع ملف PDF
- [ ] التحقق من شريط التقدم
- [ ] التحقق من المراحل الأربع
- [ ] اختبار تحميل التقرير
- [ ] فتح التقرير والتحقق من محتواه
- [ ] اختبار على متصفحات مختلفة

### الواجهة | UI Testing

- [ ] جميع النصوص باللغة العربية
- [ ] اتجاه RTL يعمل بشكل صحيح
- [ ] الألوان تظهر بشكل صحيح
- [ ] الشعار يظهر ومتمركز
- [ ] الخطوط العربية واضحة

---

## 🔄 التحديثات | Updates

```bash
# سحب آخر التغييرات | Pull latest changes
git pull origin main

# تحديث المكتبات | Update dependencies
pip install -r requirements.txt --upgrade

# إعادة تشغيل التطبيق | Restart app
streamlit run app.py
```

---

## 📊 الإحصائيات | Statistics

- **عدد الأسطر | Total Lines:** ~547 lines in app.py
- **CSS مخصص | Custom CSS:** ~280 lines
- **Python Logic:** ~267 lines
- **أنواع الملفات المدعومة | Supported File Types:** 3 (xlsx, xls, pdf)
- **مراحل المعالجة | Processing Stages:** 4
- **مدة المعالجة | Processing Duration:** 2 minutes

---

## 🎯 حالات الاستخدام | Use Cases

### 1. العروض التجريبية | Demos
- عرض للإدارة العليا
- عرض للعملاء المحتملين
- المعارض والمؤتمرات

### 2. اختبار المفهوم | Proof of Concept
- التحقق من صحة الفكرة
- جمع الملاحظات
- تقييم الاهتمام

### 3. النموذج الأولي | Prototype
- أساس للتطوير الفعلي
- مرجع للتصميم
- دليل للمطورين

---

## 📝 ملاحظات مهمة | Important Notes

### للمطورين | For Developers
- الكود منظم ومعلق بشكل جيد
- سهل التعديل والتوسيع
- يتبع أفضل الممارسات

### للمستخدمين | For Users
- واجهة بديهية لا تحتاج تدريب
- رسائل واضحة بالعربية
- تجربة سلسة ومريحة

### تحذير | Warning
⚠️ **هذا تطبيق تجريبي** - لا يتم إجراء معالجة حقيقية للبيانات
⚠️ **This is a demo app** - No actual data processing is performed

✅ التقرير المُنتج هو نموذج ثابت لأغراض العرض
✅ The generated report is a static sample for demonstration purposes

🔒 جميع الملفات المرفوعة تبقى محلية ولا يتم إرسالها إلى أي خادم
🔒 All uploaded files remain local and are not sent to any server

---

## 📞 الدعم والمساعدة | Support & Help

### الموارد | Resources
- [Streamlit Documentation](https://docs.streamlit.io)
- [Python Documentation](https://docs.python.org)
- [Arabic Typography Guidelines](https://www.w3.org/International/articles/arabic-type/)

### للعرض التجريبي | For Demo Presentation
راجع ملف `DEMO_GUIDE.md` للحصول على:
- سيناريو العرض الكامل
- نقاط رئيسية للذكر
- أسئلة وأجوبة متوقعة
- نصائح للمقدم

---

## 🏆 الإنجازات | Achievements

✅ تطبيق كامل وجاهز للاستخدام
✅ واجهة عربية 100% مع RTL كامل
✅ تصميم احترافي بألوان الفجيرة
✅ محاكاة واقعية لمدة دقيقتين
✅ توثيق شامل وكامل
✅ سهل التشغيل والاستخدام
✅ قابل للتوسع والتطوير

---

**تم التطوير بواسطة | Developed for:** حكومة الفجيرة | Fujairah Government

**التاريخ | Date:** 6 أبريل 2026 | April 6, 2026

**الإصدار | Version:** 1.0.0

**الحالة | Status:** ✅ جاهز للإنتاج | Ready for Production
