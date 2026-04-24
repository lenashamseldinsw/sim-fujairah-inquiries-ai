#!/bin/bash
# Quick validation of test results

echo "=================================="
echo "TEST RESULTS VALIDATION"
echo "=================================="

# Check report sections files exist
echo ""
echo "📁 Checking output files..."

if [ -f pipeline-test-output/report_sections_ar_*.json ]; then
  echo "✅ Arabic report sections found"
  ls -lh pipeline-test-output/report_sections_ar_*.json | tail -1
else
  echo "❌ Arabic report sections NOT found"
fi

if [ -f pipeline-test-output/report_sections_en_*.json ]; then
  echo "✅ English report sections found"
  ls -lh pipeline-test-output/report_sections_en_*.json | tail -1
else
  echo "❌ English report sections NOT found"
fi

# Run validation script
echo ""
echo "🔍 Running validation script..."
echo ""

if [ -f validate_output.py ]; then
  python validate_output.py
else
  echo "⚠️  validate_output.py not found"
fi

# Check for diagnostic prints in output
echo ""
echo "🔍 Checking for diagnostic API key prints..."
echo ""

# This would need to be run with the actual test output
# For now, just show the command to run
echo "To check API key diagnostics, search test output for:"
echo "  [GenSections] api_key present:"
echo "  [ExecSummary] Calling API"
echo "  [Methodology] Calling API"
