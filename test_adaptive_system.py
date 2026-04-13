#!/usr/bin/env python
"""
Test script for the adaptive report extraction system.

Usage:
    python test_adaptive_system.py              # Test default report
    python test_adaptive_system.py --clear      # Clear cache first
    python test_adaptive_system.py --report path/to/report.docx  # Test specific report
"""

import argparse
import sys
from pathlib import Path
import glob

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from analysis.adaptive_extractor import AdaptiveReportExtractor
from analysis.report_structure_detector import ReportStructureDetector


def find_default_report():
    """Find the default report in inquiries-output directory."""
    docx_files = glob.glob('inquiries-output/*.docx')
    # Filter out temp files (starting with ~$)
    docx_files = [f for f in docx_files if not f.split('/')[-1].startswith('~$')]
    
    if not docx_files:
        print("❌ No .docx files found in outputs directory")
        return None
    return docx_files[0]


def test_extraction(report_path: str, force_refresh: bool = False):
    """Test extraction for a given report."""
    print(f"\n{'='*70}")
    print(f"Testing Adaptive Report Extraction")
    print(f"{'='*70}")
    print(f"Report: {report_path}")
    print(f"Force refresh: {force_refresh}")
    
    # Initialize extractor
    extractor = AdaptiveReportExtractor()
    
    if force_refresh:
        print("\n🔄 Clearing cache...")
        extractor.clear_cache()
    
    # First extraction
    print(f"\n{'='*70}")
    print("EXTRACTION RUN")
    print(f"{'='*70}")
    
    try:
        report = extractor.extract_report(report_path, force_refresh=force_refresh)
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Display results
    print(f"\n✅ Successfully extracted report structure")
    print(f"\nDocument: {report['document_name']}")
    print(f"Sections found: {len(report['sections'])}")
    print(f"Charts found: {len(report.get('charts', []))}")
    
    print(f"\n{'='*70}")
    print("SECTIONS BREAKDOWN")
    print(f"{'='*70}")
    
    total_tables = 0
    for idx, section in enumerate(report['sections'], 1):
        tables_count = len(section.get('tables', []))
        total_tables += tables_count
        
        print(f"\n{idx}. {section['title']}")
        print(f"   English: {section.get('title_en', 'N/A')}")
        print(f"   Level: {section.get('level', 'N/A')}")
        print(f"   Tables: {tables_count}")
        
        if section.get('content'):
            content_preview = section['content'][:100].replace('\n', ' ')
            print(f"   Content: {content_preview}...")
    
    print(f"\n{'='*70}")
    print(f"Total tables across all sections: {total_tables}")
    print(f"{'='*70}")
    
    # Test cache loading
    print(f"\n{'='*70}")
    print("CACHE TEST")
    print(f"{'='*70}")
    
    print("\n🔄 Loading from cache...")
    report2 = extractor.extract_report(report_path)
    print(f"✅ Successfully loaded from cache")
    print(f"   Sections: {len(report2['sections'])}")
    
    # Show cached reports
    print(f"\n{'='*70}")
    print("CACHED REPORTS")
    print(f"{'='*70}")
    
    cached = extractor.list_cached_reports()
    for cache_info in cached:
        print(f"\n📄 {cache_info['document_name']}")
        print(f"   Sections: {cache_info['sections_count']}")
        print(f"   Cache file: {cache_info['cache_file']}")
    
    print(f"\n{'='*70}")
    print("✅ ALL TESTS PASSED")
    print(f"{'='*70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test the adaptive report extraction system'
    )
    parser.add_argument(
        '--report',
        type=str,
        help='Path to Word document to test (default: auto-find in inquiries-output/)'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear cache before testing'
    )
    
    args = parser.parse_args()
    
    # Determine report path
    if args.report:
        report_path = args.report
        if not Path(report_path).exists():
            print(f"❌ Report not found: {report_path}")
            sys.exit(1)
    else:
        report_path = find_default_report()
        if not report_path:
            sys.exit(1)
    
    # Run tests
    test_extraction(report_path, force_refresh=args.clear)


if __name__ == '__main__':
    main()
