.PHONY: help demo real real-unified real-single install clean

# Default target
help:
	@echo "Fujairah Pulse - AI Analysis Platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make demo           - Run the demo version with simulated outputs"
	@echo "  make real-unified   - Run the real version with BOTH inquiries + complaints (recommended)"
	@echo "  make real-single    - Run the real version with SINGLE flow (legacy)"
	@echo "  make real           - Alias for real-unified"
	@echo "  make install        - Install dependencies from requirements.txt"
	@echo "  make clean          - Clean up cache and temporary files"
	@echo ""
	@echo "Quick start:"
	@echo "  make demo           # Start with demo mode"
	@echo "  make real-unified   # Start with unified real app (both flows)"

# Install dependencies
install:
	pip install -r requirements.txt

# Run demo version
demo:
	@echo "Starting Fujairah Pulse in DEMO mode..."
	cd demo && streamlit run app.py --logger.level=warning

# Run real version - unified app (both flows) - RECOMMENDED
real-unified:
	@echo "Starting Fujairah Pulse in REAL mode (UNIFIED - both flows)..."
	cd real && streamlit run app_inq_comp.py --logger.level=warning

# Run real version - single flow (legacy)
real-single:
	@echo "Starting Fujairah Pulse in REAL mode (SINGLE - inquiries only)..."
	cd real && streamlit run app.py --logger.level=warning

# Default to unified
real: real-unified

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "Cleaned up temporary files"
