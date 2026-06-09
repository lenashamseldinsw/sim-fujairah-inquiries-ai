# Demo Version - Stable Pre-built Reports

## Overview

The **demo version** displays pre-built, fully-extracted reports with **automatic caching** for instant loads. No AI analysis happens here—this is the stable, production-ready interface.

**Key Feature**: Adaptive Report System that auto-detects report structure and caches results.

---

## 🚀 Running the Demo

```bash
cd demo
streamlit run app.py
```

Opens at `http://localhost:8501`

Or from project root:
```bash
make demo
```

---

## ✨ Features

- ✅ **100% Arabic UI** with full RTL support
- 📦 **Pre-built Reports**: Sample inquiries and complaints reports included
- ⚡ **Smart Caching**: Automatic extraction caching for instant report loads
- 🔍 **Auto-Detection**: Detects report structure from Word headings
- 📊 **Dynamic Display**: Sections, tables, and charts render automatically
- 🔒 **Offline**: No external servers, all data stays local

---

## 📁 Folder Structure

```
demo/
├── app.py                          # Main Streamlit app
├── .env                            # Environment config (APP_MODE=demo)
├── analysis/                       # Demo analyzer with extraction
│   ├── __init__.py                # Exports all demo components
│   ├── base.py                    # Abstract Analyzer interface
│   ├── demo.py                    # DemoAnalyzer (simulated processing)
│   ├── dynamic_display.py         # Dynamic report display
│   ├── adaptive_extractor.py      # Extract + cache reports
│   └── report_structure_detector.py  # Auto-detect report structure
├── inquiries-output/              # Sample inquiries reports & cache
├── complaints-output/             # Sample complaints reports & cache
└── test_adaptive_system.py        # Test extraction utilities
```

---

## 🎯 How It Works

### Step-by-Step Flow

1. **User uploads file** → `DemoAnalyzer` simulates processing with progress bars
2. **Demo analyzer** returns immediately (simulated)
3. **Display handler** calls `AdaptiveReportExtractor.extract_report()`
4. **Extractor checks cache** → If JSON exists, loads instantly from `cache/`
5. **If no cache** → Extracts structure from Word document (slow first time)
6. **Saves cache** → Creates JSON file in `cache/` for future loads
7. **Displays dynamically** → Renders sections, tables, charts based on extracted structure

### Caching in Action

- **First load of a report**: Extracts from Word → slow (~5 sec)
- **Subsequent loads**: Uses `cache/[hash].json` → instant
- **Force refresh**: Call with `force_refresh=True` to bypass cache

---

## 📊 Sample Reports

### Inquiries Flow
- **File**: `inquiries-output/تقرير تحليل استفسارات المتعاملين.docx`
- **Cache**: `inquiries-output/cache/[hash].json`

### Complaints Flow
- **File**: `complaints-output/تقرير تحليل شكاوى المتعاملين.docx`
- **Cache**: `complaints-output/cache/[hash].json`

---

## 🔧 Key Components

### DemoAnalyzer (`analysis/demo.py`)
Simulates file processing with realistic progress stages:
- File upload and validation (0-25%)
- Data analysis and extraction (25-50%)
- Processing (50-75%)
- Report generation (75-100%)

Returns immediately with simulated report structure.

### AdaptiveReportExtractor (`analysis/adaptive_extractor.py`)
Automatically extracts report structure from Word documents:
- Detects sections from heading styles
- Assigns tables to nearest section
- **Caches extracted JSON** for instant subsequent loads
- Handles both inquiries and complaints reports

### DynamicReportDisplay (`analysis/dynamic_display.py`)
Renders extracted reports dynamically:
- Creates tabs for each section
- Renders tables with Arabic headers
- Displays charts and visualizations
- **Automatically uses cached JSON** if available

### ReportStructureDetector (`analysis/report_structure_detector.py`)
Auto-detects report structure without hardcoding:
- Parses Word heading styles
- Builds hierarchical section tree
- Identifies tables and charts
- Works with any report format

---

## 🧪 Testing

Run the extraction tests:

```bash
cd demo
python test_adaptive_system.py
```

This tests:
- Report extraction from Word documents
- Cache creation and reuse
- Structure detection accuracy

---

## 🔄 Workflow

### Development (demo/ folder)

Edit these files:
- **UI changes**: `app.py`
- **Report display**: `analysis/dynamic_display.py`
- **Extraction logic**: `analysis/adaptive_extractor.py`
- **Report structure detection**: `analysis/report_structure_detector.py`

### Testing

```bash
# Extract and cache reports
python test_adaptive_system.py

# Run the app
streamlit run app.py
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Report file not found | Check files exist in `inquiries-output/` or `complaints-output/` with correct Arabic names |
| Cache not being used | Delete `*/cache/` folders, re-run to regenerate |
| Extraction is slow | This is normal on first load (Word parsing); subsequent loads use cache |
| Sections not detected | Ensure Word document uses proper heading styles for section titles |
| Import errors | Make sure you're in `demo/` folder and `.env` exists with `APP_MODE=demo` |

---

## 📝 .env Configuration

```
APP_MODE=demo
```

Required in `demo/.env` so the app knows to use DemoAnalyzer.

---

## 🌍 Deployment

### Streamlit Cloud

1. Push repo to GitHub
2. Go to https://streamlit.io/cloud
3. Select repo and file: `demo/app.py`
4. Deploy

### Docker

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY demo/ .
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
```

```bash
docker build -t fujairah-demo .
docker run -p 8501:8501 fujairah-demo
```

---

## 📚 Related Documentation

- **[../CLAUDE.md](../CLAUDE.md)**: Full development guide and architecture
- **[../README.md](../README.md)**: Project overview and quick links
- **[../real/README.md](../real/README.md)**: Real version (AI analysis) documentation

---

**Note**: This is a **demo/stable version** with pre-built reports. For AI-powered real analysis, see the `real/` folder.
