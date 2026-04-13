# Complaints Use Case Flow

## Overview

The Complaints flow is a specialized analysis pipeline designed for processing and analyzing citizen complaints in the Fujairah Pulse system. This document describes the demo implementation and how it differs from the Inquiries flow.

## Flow Architecture

### Dual Flow System

The platform supports two distinct analysis flows:

1. **Inquiries Flow** - Analyzes citizen inquiries/questions
   - Outputs saved to: `inquiries-output/`
   - Cache location: `inquiries-output/cache/`
   - User downloads from: Inquiries tab in the UI

2. **Complaints Flow** - Analyzes citizen complaints
   - Outputs saved to: `complaints-output/`
   - User downloads from: Complaints tab in the UI
   - Each flow has independent output management

## Complaints Flow Pipeline

### User Journey

1. **Navigate to Complaints Tab** → Select the Complaints flow
2. **Upload File** → User selects a complaints Word document
3. **File Validation** → System validates format and size
4. **Processing** → Simulated analysis with visible progress stages
5. **Report Display** → Dynamic display of complaint analysis results
6. **Download Output** → User downloads processed report and analysis files

### Processing Stages

The Complaints flow includes realistic processing stages with progress tracking:

```python
COMPLAINTS_STAGES = [
    {"start": 0,    "end": 7.5,  "progress_start": 0,   "progress_end": 25},   # Stage 1
    {"start": 7.5,  "end": 15,   "progress_start": 25,  "progress_end": 50},   # Stage 2
    {"start": 15,   "end": 22.5, "progress_start": 50,  "progress_end": 75},   # Stage 3
    {"start": 22.5, "end": 30,   "progress_start": 75,  "progress_end": 100},  # Stage 4
]
```

**Total Processing Time**: ~30 seconds (simulated)

### Output Files

Users can download the following files from the Complaints flow:

| File | Location | Purpose |
|------|----------|---------|
| Complaint Report (Word) | `complaints-output/*.docx` | Detailed analysis of complaints |
| Triage Analysis (Excel) | `complaints-output/*.xlsx` | Structured complaint categorization |
| JSON Cache | `complaints-output/cache/` | Cached structure for fast reload |

## Demo Mode Implementation

### How the Demo Works

1. **User uploads complaints file** → `app.py` calls `DemoAnalyzer`
2. **DemoAnalyzer** simulates processing with realistic timing
3. **After simulation**, complaint results are displayed dynamically
4. **Display renders** extracted structure with sections, tables, and charts
5. **User can download** the complete analysis package from `complaints-output/`

### File Structure

The complaints flow uses the same adaptive extraction system as inquiries:

```python
from analysis import DynamicReportDisplay, AdaptiveReportExtractor

# Extract complaints report
extractor = AdaptiveReportExtractor()
report = extractor.extract_report("complaints-output/your_report.docx")

# Display with dynamic rendering
display = DynamicReportDisplay(lang='ar')
display.display_report("complaints-output/your_report.docx")
```

## Output Management

### Complaints Output Folder Structure

```
complaints-output/
├── *.docx                    # Processed complaint reports
├── *.xlsx                    # Triage and analysis spreadsheets
└── cache/                    # JSON cache for fast reloading
    └── [hash].json          # Extracted structure cache
```

### Download Behavior

When a user completes the Complaints flow:
- All output files are automatically prepared in `complaints-output/`
- User can download a ZIP containing:
  - Word report with detailed analysis
  - Excel spreadsheet with categorized complaints
- Subsequent uploads reuse cached data for instant display

### Cache Management

- **Automatic Caching**: Report structure is automatically cached in JSON
- **Cache Invalidation**: Cache updates when file size or modification time changes
- **Manual Refresh**: Can force refresh to bypass cache if needed

## UI Integration

### Complaints Tab in app.py

The Complaints flow is integrated into the Streamlit UI with:

```python
# Check for complaints report file
report_path = Path("complaints-output/[complaint_report_filename].docx")
if report_path.exists():
    zip_data = create_download_zip()  # Prepares download
    st.download_button(
        label=tx['btn_download_cmp'],  # "Download Complaints Report"
        data=zip_data,
        file_name="complaints_analysis.zip",
        mime="application/zip"
    )
```

## Processing Stages Detail

### Stage 1: Data Ingestion (0-25%)
- File upload and validation
- Extract complaint document structure
- Initialize processing pipeline

### Stage 2: Content Analysis (25-50%)
- Analyze complaint categories
- Extract complaint metadata
- Identify key complaint topics

### Stage 3: Triage & Categorization (50-75%)
- Categorize complaints by type
- Assign priority levels
- Generate category summary

### Stage 4: Report Generation (75-100%)
- Create final analysis report
- Generate Excel triage spreadsheet
- Cache extracted structure
- Prepare download package

## Differences from Inquiries Flow

| Aspect | Inquiries Flow | Complaints Flow |
|--------|----------------|-----------------|
| **Output Folder** | `inquiries-output/` | `complaints-output/` |
| **File Naming** | Inquiry analysis files | Complaint analysis files |
| **Report Type** | Inquiry resolution tracking | Complaint categorization |
| **Triage Focus** | Inquiry complexity | Complaint severity & type |
| **Download Button** | "Download Inquiry Report" | "Download Complaints Report" |
| **User Tab** | Inquiries tab | Complaints tab |

## Configuration

### APP_MODE

Both Inquiries and Complaints flows use the same analyzer implementation:
- `APP_MODE=demo` → Uses DemoAnalyzer with simulated processing
- `APP_MODE=real` → Uses RealAnalyzer (for real agentic analysis)

### Environment Files

```bash
# For demo (inquiries + complaints with simulation)
cp .env.demo .env
streamlit run app.py

# For real (inquiries + complaints with real AI analysis)
cp .env.real .env
streamlit run app.py
```

## Troubleshooting

### "Report file not found" (Complaints mode)

Check that the complaints report exists at:
```bash
ls -la complaints-output/*.docx
```

The system looks for any .docx file in the `complaints-output/` folder.

### Cache not being used in Complaints flow

The cache is automatically created and used. Check:
```bash
ls -la complaints-output/cache/
```

To verify cache is working, process the same complaints file twice—the second load should be instant.

### Different outputs for Inquiries vs Complaints

Ensure you're:
1. In the correct flow tab (Inquiries vs Complaints)
2. Uploading files to the correct input folder
3. Downloading from the correct output folder:
   - Inquiries flow → `inquiries-output/`
   - Complaints flow → `complaints-output/`

## Future Development

### Real Implementation (real branch)

The real Complaints analyzer will:
- Use Claude API for intelligent complaint analysis
- Deploy agentic workflows for complaint routing
- Generate AI-powered categorization and recommendations
- Maintain the same output structure and download interface

### Extending Complaints Analysis

To improve the complaints pipeline:

1. **Add new triage categories** - Update complaint taxonomy
2. **Improve categorization logic** - Enhance the AI analysis
3. **Add new report sections** - Expand output structure
4. **Custom metrics** - Add complaint-specific KPIs

## See Also

- [ADAPTIVE_SYSTEM_SUMMARY.md](./ADAPTIVE_SYSTEM_SUMMARY.md) - Extraction and caching system
- [WORKFLOW.md](./WORKFLOW.md) - General workflow overview
- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - Quick start guide
