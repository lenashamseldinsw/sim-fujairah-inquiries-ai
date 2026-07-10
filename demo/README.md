# Demo Version — Stable Pre-built Reports

## Overview

The **demo version** displays pre-built, fully-extracted reports with **automatic caching** for instant loads. No AI analysis happens here — file uploads are simulated and the app renders reports that already exist on disk. This is the stable, presentation-ready interface.

**Key feature:** Adaptive Report System that auto-detects report structure from Word headings and caches the extracted JSON.

---

## 🚀 Running the Demo

```bash
# From project root
make demo

# Or manually
cd demo && streamlit run app.py
```

Opens at `http://localhost:8501`.

---

## ✨ Features

- ✅ **100% Arabic UI** with full RTL support
- 📦 **Pre-built reports** for inquiries and complaints, organized by period
- ⚡ **Smart caching** — extracted structure cached as JSON for instant re-loads
- 🔍 **Auto-detection** — sections detected from Word heading styles (no hardcoding)
- 📊 **Dynamic display** — sections, tables, and charts render from whatever is detected
- 🔒 **Offline** — no external servers; all files stay local

---

## 📁 Folder Structure

```
demo/
├── app.py                              # Main Streamlit app
├── chart_parser.py                     # Chart XML parsing utilities
├── .env                                # APP_MODE=demo
├── test_adaptive_system.py             # Extraction test script
├── analysis/
│   ├── __init__.py                     # Exports demo components
│   ├── base.py                         # Abstract Analyzer interface
│   ├── demo.py                         # DemoAnalyzer (simulated processing)
│   ├── dynamic_display.py              # DynamicReportDisplay (renders reports)
│   ├── adaptive_extractor.py           # AdaptiveReportExtractor (extract + cache)
│   └── report_structure_detector.py    # ReportStructureDetector (auto-detect)
├── inquiries-output/                   # Inquiries reports, organized by period
│   ├── 2025/                           # Full-year sample report + Excel
│   ├── Q1-2026/                        # Quarterly report + Excel
│   └── cache/                          # Cached extraction JSON
└── complaints-output/                  # Complaints reports, organized by period
    ├── 2025/
    ├── Q1-2026/
    └── cache/
```

Report files inside each period folder are named in Arabic, e.g.:
- `inquiries-output/Q1-2026/تقرير تحليل استفسارات المتعاملين — الربع الأول 2026.docx`
- `complaints-output/Q1-2026/تقرير تحليل شكاوى المتعاملين — 2026.docx`

---

## 🎯 How It Works

1. **User uploads a file** → `DemoAnalyzer` simulates processing with progress stages (no real analysis).
2. **Display handler** calls `AdaptiveReportExtractor.extract_report(path)` for the matching pre-built report.
3. **Extractor checks the cache** → if `cache/[hash].json` exists, loads instantly.
4. **On cache miss** → parses the Word document via `ReportStructureDetector`, then writes the JSON cache.
5. **`DynamicReportDisplay`** renders the structure: a tab per section, tables with Arabic headers, and charts.

### Caching behaviour

- **First load of a report:** extracts from Word (~5–10 s).
- **Subsequent loads:** reads `cache/[hash].json` (~instant).
- **Force refresh:** `extractor.extract_report(path, force_refresh=True)`.
- Cache key is derived from filename + modification time + size, so editing the source `.docx` invalidates the cache automatically.

---

## 🔑 Key Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `DemoAnalyzer` | `analysis/demo.py` | Simulates processing; defines progress stages; loads pre-built reports |
| `AdaptiveReportExtractor` | `analysis/adaptive_extractor.py` | Extracts report structure from Word; manages JSON cache |
| `ReportStructureDetector` | `analysis/report_structure_detector.py` | Detects sections/tables/charts from heading styles + formatting |
| `DynamicReportDisplay` | `analysis/dynamic_display.py` | Renders extracted structure as Streamlit tabs, tables, charts (auto-uses cache) |
| `Analyzer` | `analysis/base.py` | Abstract interface all analyzers implement |

---

## 🧪 Testing

```bash
cd demo
python test_adaptive_system.py
```

Exercises report extraction, cache creation/reuse, and structure detection.

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Report file not found | Confirm the `.docx` exists in the right period subfolder (`2025/` or `Q1-2026/`); watch for trailing spaces in Arabic filenames |
| Cache not being used | Delete the `cache/` folder in the relevant output dir and re-run |
| First load is slow | Expected — Word parsing runs once, then the cache serves subsequent loads |
| Sections not detected | Ensure the Word document uses proper heading styles for section titles |
| `ModuleNotFoundError: analysis` | Run from inside `demo/` (or use `make demo`); confirm `.env` has `APP_MODE=demo` |

---

## 🌍 Deployment (Streamlit Cloud)

1. Push the repo to GitHub.
2. On https://streamlit.io/cloud, select the repo and set the entry file to `demo/app.py`.
3. Deploy.

---

## 📚 Related Docs

- **[../CLAUDE.md](../CLAUDE.md)** — full development guide and architecture
- **[../README.md](../README.md)** — project overview and navigation
- **[../real/README.md](../real/README.md)** — real (AI-powered) version

---

**Note:** This is the **stable demo** with pre-built reports. For AI-powered analysis, see the `real/` folder.
