# Quick Start Guide - نبض الفجيرة

## Running the Application

### Start the Streamlit App
```bash
cd /Users/lena/Documents/Sword/sim-fujairah-inquiries-ai
streamlit run app.py
```

The application will open in your default browser at `http://localhost:8501`

## Application Flow

### 1. Landing Page (Home)
When you first open the application, you'll see:
- **Hero section** with the system name and description
- **"ابدأ التحليل الآن" button** - Click to go to analysis page
- **Features section** - Shows the 3 main benefits
- **How it works** - 4-step process explanation

### 2. Navigation to Analysis Page
- Click the **"🚀 ابدأ التحليل الآن"** button on the landing page
- You'll be taken to the analysis page
- The **logo** remains visible in the top left
- A **"← العودة للرئيسية"** button appears in the top right

### 3. Analysis Page - Upload
- See the **"رفع الملفات"** section
- Upload an Excel (.xlsx, .xls) or PDF file
- File information will be displayed (name, size, type)
- Click **"🚀 بدء التحليل والمعالجة"** to start processing

### 4. Analysis Page - Processing
- Watch the progress through 4 stages:
  1. 📤 **جاري رفع الملفات** (0-25%)
  2. 📊 **تحليل البيانات** (25-50%)
  3. 🤖 **معالجة الاستفسارات** (50-75%)
  4. 📝 **إنشاء التقرير النهائي** (75-100%)
- Each stage shows:
  - Icon
  - Processing badge
  - Stage title and description
  - Progress bar
  - Percentage

### 5. Analysis Page - Completion
- See the success message: **"✅ تم إنشاء التقرير بنجاح!"**
- Click **"📥 تحميل التقرير الشامل"** to download the Word document
- Click **"🔄 تحليل ملف جديد"** to analyze another file
- Click **"← العودة للرئيسية"** to return to the landing page

## Key Features

### Logo
- **Location**: Top left corner
- **Size**: 180px width
- **File**: `assets/fujairah-police-logo.png`
- **Visibility**: Present on all pages

### Color Scheme
- **Primary**: Dark Green (#1a6b3c) - Headers, buttons, footer
- **Accent**: Gold (#B68A35) - Borders, highlights, CTA button
- **Background**: White (#FFFFFF) - Clean, professional
- **Text**: Charcoal (#2C2C2C) - High readability

### Buttons
- **CTA Button** (Landing): Large gold button with white border
- **Primary Buttons** (Analysis): Dark green → Gold on hover
- **Download Button**: Gold → Dark green on hover
- **Back Button**: Standard style in top right

### Animations
- **Cards**: Fade in on load
- **Upload Icon**: Pulse animation
- **Buttons**: Lift on hover
- **Progress**: Smooth transitions

## File Requirements

### Supported Formats
- Excel: `.xlsx`, `.xls`
- PDF: `.pdf`

### File Size
- Maximum: 200 MB

### Expected Content
- Customer inquiries/questions
- Data suitable for AI analysis

## Troubleshooting

### Logo Not Showing
- Ensure `assets/fujairah-police-logo.png` exists
- Check file permissions
- Verify file path is correct

### Streamlit Port Already in Use
```bash
# Kill existing Streamlit process
pkill -f streamlit

# Or use a different port
streamlit run app.py --server.port 8502
```

### Page Not Loading
- Clear browser cache
- Try incognito/private mode
- Check browser console for errors

### Styling Issues
- Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
- Clear Streamlit cache: Delete `.streamlit/cache/` folder

## Customization

### Change Colors
Edit the color constants in `app.py`:
```python
DARK_GREEN = "#1a6b3c"
GOLD = "#B68A35"
OLIVE_GREEN = "#6B8E23"
# ... etc
```

### Modify Text
All Arabic text is in the `app.py` file:
- Landing page: In `landing_page()` function
- Analysis page: In `analysis_page()` function
- Headers, buttons, messages: Throughout the file

### Adjust Processing Time
Modify the `STAGES` list in `app.py`:
```python
STAGES = [
    {"start": 0, "end": 30, ...},  # Adjust timing here
    # ...
]
```

## Documentation Files

1. **DESIGN_GUIDE.md** - Comprehensive design system documentation
2. **UI_REDESIGN_SUMMARY.md** - Summary of all changes made
3. **VISUAL_REFERENCE.md** - Visual layout and styling reference
4. **QUICK_START.md** - This file

## Support

For issues or questions:
1. Check the documentation files
2. Review the code comments in `app.py`
3. Check Streamlit documentation: https://docs.streamlit.io

## Version Information

- **Streamlit**: Latest version
- **Python**: 3.7+
- **Fonts**: Cairo, Tajawal (loaded from Google Fonts)
- **Icons**: Unicode emojis (universal support)

## Production Deployment

### Streamlit Cloud
1. Push code to GitHub
2. Connect to Streamlit Cloud
3. Deploy from repository

### Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
```

### Server Deployment
```bash
# Install dependencies
pip install -r requirements.txt

# Run with nohup
nohup streamlit run app.py --server.port 8501 &

# Or use systemd service
```

## Best Practices

1. **Always test** after making changes
2. **Keep backups** of working versions
3. **Document changes** in code comments
4. **Test on multiple browsers**
5. **Verify mobile responsiveness**
6. **Check RTL rendering** for Arabic text
7. **Validate file uploads** before processing
8. **Monitor performance** with large files

## Next Steps

1. Add your actual AI processing logic
2. Connect to your data sources
3. Implement report generation
4. Add user authentication (if needed)
5. Set up analytics tracking
6. Configure error logging
7. Optimize for production
