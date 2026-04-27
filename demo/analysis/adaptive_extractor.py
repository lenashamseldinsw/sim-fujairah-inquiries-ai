"""Adaptive report extractor with caching and auto-detection."""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from docx import Document

from .report_structure_detector import ReportStructureDetector
from chart_parser import extract_charts_from_docx


class AdaptiveReportExtractor:
    """
    Adaptive report extraction with automatic structure detection and caching.

    Features:
    - Auto-detects sections from Word document headings
    - Auto-assigns tables to sections based on proximity
    - Caches extracted data in JSON to avoid re-processing
    - Works with any Word report structure
    """

    # Increment this when extraction logic changes to invalidate old cache
    EXTRACTION_VERSION = 16

    def __init__(self, cache_dir: str = None, docx_path: str = None):
        """
        Initialize extractor and ensure cache directory exists.

        Args:
            cache_dir: Directory to store cache files (default: auto-detected from docx_path)
            docx_path: Path to document (used to auto-detect cache folder if cache_dir not specified)
        """
        if cache_dir is None:
            # Auto-detect cache folder based on document path
            cache_dir = self._detect_cache_dir(docx_path)

        self.CACHE_DIR = Path(cache_dir)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _detect_cache_dir(self, docx_path: str = None) -> str:
        """
        Auto-detect cache directory based on document path.

        Each output folder (inquiries-output, complaints-output) has its own cache subdirectory.
        English documents use english-cache subfolder.

        Args:
            docx_path: Path to the document

        Returns:
            Path to appropriate cache directory
        """
        app_dir = Path(__file__).parent.parent

        # Detect report type and language from path
        if docx_path:
            path_str = str(docx_path).lower()
            is_english = 'english-output' in path_str

            if 'complaints' in path_str:
                cache_path = app_dir / "complaints-output" / "cache"
                if is_english:
                    return str(cache_path / "english-cache")
                return str(cache_path)
            elif 'inquiries' in path_str:
                return str(app_dir / "inquiries-output" / "cache")

        # Default to inquiries if can't detect
        return str(app_dir / "inquiries-output" / "cache")

    def extract_report(self, docx_path: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Extract report structure and data with caching.

        Args:
            docx_path: Path to Word document
            force_refresh: If True, bypass cache and re-extract

        Returns:
            Dictionary with complete report structure
        """
        doc_path = Path(docx_path)

        # Set cache directory based on document path (report-specific caching)
        self.CACHE_DIR = Path(self._detect_cache_dir(docx_path))
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Determine cache file path (needed for both cache check and save)
        is_english = 'english-output' in str(docx_path).lower()
        if is_english:
            docx_path_str = str(docx_path).lower()
            json_filename = None
            # Map periods to their English JSON files
            if 'q1-2026' in docx_path_str or 'q1_2026' in docx_path_str:
                json_filename = 'Q1_2026_complaints_analysis_en.json'
            elif '2025' in docx_path_str:
                json_filename = 'complaints_analysis_2025_en.json'
            cache_file = self.CACHE_DIR / json_filename if json_filename else self.CACHE_DIR / "cache.json"
        else:
            # Arabic flow: Use hash-based cache key
            cache_key = self._generate_cache_key(doc_path)
            cache_file = self.CACHE_DIR / f"{cache_key}.json"

        # Check cache first (unless force refresh)
        if not force_refresh:
            if is_english:
                if cache_file.exists():
                    cached_report = self._load_from_cache(cache_file)
                    print(f"✓ Loading cached report structure from: {cache_file.name}")
                    return cached_report
            else:
                # Arabic flow: Use hash-based cache key (original behavior)
                if cache_file.exists():
                    cached_report = self._load_from_cache(cache_file)
                    # Verify cache version matches current extraction logic
                    if cached_report.get('extraction_version') == self.EXTRACTION_VERSION:
                        print(f"✓ Loading cached report structure from: {cache_file.name}")
                        return cached_report
                    else:
                        print(f"✓ Cache invalidated (extraction logic updated). Re-extracting from: {doc_path.name}")

        print(f"✓ Extracting report structure from: {doc_path.name}")

        # Extract structure using detector
        detector = ReportStructureDetector(str(doc_path))
        structure = detector.detect_structure()

        # Extract charts with actual data
        charts = extract_charts_from_docx(str(doc_path))

        # Build complete report structure
        report = self._build_report_structure(structure, charts, doc_path)

        # Save to cache
        self._save_to_cache(report, cache_file)
        print(f"✓ Cached report structure to: {cache_file.name}")

        return report

    def _generate_cache_key(self, doc_path: Path) -> str:
        """
        Generate unique cache key based on filename and modification time.

        This ensures cache is invalidated when file changes.
        """
        # Get file stats
        file_stat = doc_path.stat()
        mtime = str(file_stat.st_mtime)
        size = str(file_stat.st_size)

        # Create hash from filename + mtime + size
        key_string = f"{doc_path.name}_{mtime}_{size}"
        hash_obj = hashlib.md5(key_string.encode())

        return hash_obj.hexdigest()

    def _build_report_structure(
        self,
        structure: Dict[str, Any],
        charts: list,
        doc_path: Path
    ) -> Dict[str, Any]:
        """
        Build complete report structure combining detected structure and chart data.

        Args:
            structure: Detected structure from ReportStructureDetector
            charts: Chart data from chart_parser
            doc_path: Original document path

        Returns:
            Complete report structure ready for display
        """
        # Debug: Log what we're working with
        print(f"📊 Charts extracted: {len(charts)}")
        print(f"📍 Sections detected: {len(structure['sections'])}")

        report = {
            'extraction_version': self.EXTRACTION_VERSION,
            'document_name': doc_path.name,
            'document_path': str(doc_path),
            'metadata': structure['metadata'],
            'charts': charts,
            'sections': []
        }

        # Convert sections to display-friendly format
        for section in structure['sections']:
            section_data = {
                'id': section['id'],
                'title': section['title_ar'],
                'title_en': section['title_en'],
                'level': section['level'],
                'content': section['content'],
                'tables': [],
                'charts': [],
                'subsections': []
            }

            # Add tables assigned to this main section
            for table_info in section['tables']:
                table_data = table_info['data']
                table_data['original_index'] = table_info['index']
                # Include dynamically detected caption if available
                if table_info.get('caption'):
                    table_data['caption'] = table_info['caption']
                section_data['tables'].append(table_data)

            # Add charts assigned to this main section
            for chart_info in section.get('charts', []):
                # Use the chart index to get the actual chart data
                chart_idx = chart_info.get('index')
                if chart_idx is not None and chart_idx < len(charts):
                    chart_data = charts[chart_idx]
                    section_data['charts'].append(chart_data)
                    print(f"  ✓ Chart {chart_idx} assigned to section: {section['title_ar']}")
                else:
                    print(f"  ⚠ Chart index {chart_idx} out of range (only {len(charts)} charts available)")

            # Add subsections with their tables
            for subsec in section.get('subsections', []):
                subsec_data = {
                    'id': subsec['id'],
                    'title': subsec['title_ar'],
                    'title_en': subsec['title_en'],
                    'level': subsec['level'],
                    'content': subsec['content'],
                    'tables': [],
                    'charts': []
                }

                # Add tables assigned to this subsection
                for table_info in subsec['tables']:
                    table_data = table_info['data']
                    table_data['original_index'] = table_info['index']
                    # Include dynamically detected caption if available
                    if table_info.get('caption'):
                        table_data['caption'] = table_info['caption']
                    subsec_data['tables'].append(table_data)

                # Add charts assigned to this subsection
                for chart_info in subsec.get('charts', []):
                    # Use the chart index to get the actual chart data
                    chart_idx = chart_info.get('index')
                    if chart_idx is not None and chart_idx < len(charts):
                        chart_data = charts[chart_idx]
                        subsec_data['charts'].append(chart_data)
                        print(f"  ✓ Chart {chart_idx} assigned to subsection: {subsec['title_ar']}")
                    else:
                        print(f"  ⚠ Chart index {chart_idx} out of range for subsection")

                section_data['subsections'].append(subsec_data)

            report['sections'].append(section_data)

        return report

    def _save_to_cache(self, report: Dict[str, Any], cache_file: Path) -> None:
        """Save report structure to JSON cache file."""
        # Create a cache-friendly version (remove non-serializable data if any)
        cache_data = self._prepare_for_cache(report)

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    def _load_from_cache(self, cache_file: Path) -> Dict[str, Any]:
        """Load report structure from JSON cache file."""
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _prepare_for_cache(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare report data for JSON serialization.

        Removes or converts any non-serializable objects.
        """
        import copy
        cache_data = copy.deepcopy(report)

        # Remove raw_xml from charts (binary data)
        if 'charts' in cache_data:
            for chart in cache_data['charts']:
                if 'raw_xml' in chart:
                    del chart['raw_xml']

        return cache_data

    def clear_cache(self, doc_name: Optional[str] = None) -> None:
        """
        Clear cached reports.

        Args:
            doc_name: If provided, clear only cache for this document.
                     If None, clear all cache.
        """
        if doc_name:
            # Clear specific document cache
            for cache_file in self.CACHE_DIR.glob("*.json"):
                cached_report = self._load_from_cache(cache_file)
                if cached_report.get('document_name') == doc_name:
                    cache_file.unlink()
                    print(f"✓ Cleared cache for: {doc_name}")
        else:
            # Clear all cache
            for cache_file in self.CACHE_DIR.glob("*.json"):
                cache_file.unlink()
            print("✓ Cleared all cached reports")

    def list_cached_reports(self) -> list[Dict[str, str]]:
        """
        List all cached reports.

        Returns:
            List of dictionaries with cache info
        """
        cached_reports = []

        for cache_file in self.CACHE_DIR.glob("*.json"):
            try:
                report = self._load_from_cache(cache_file)
                cached_reports.append({
                    'cache_file': cache_file.name,
                    'document_name': report.get('document_name', 'Unknown'),
                    'sections_count': len(report.get('sections', [])),
                    'modified': cache_file.stat().st_mtime
                })
            except Exception:
                pass

        return cached_reports


# Legacy function for backward compatibility
def extract_full_report(docx_path: str) -> Dict[str, Any]:
    """
    Extract full report with automatic structure detection and caching.

    This is the main entry point that maintains backward compatibility
    while using the new adaptive extraction system.

    Args:
        docx_path: Path to Word document

    Returns:
        Dictionary with complete report structure
    """
    extractor = AdaptiveReportExtractor()
    return extractor.extract_report(docx_path)
