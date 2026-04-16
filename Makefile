.PHONY: help demo real install clean

# Default target
help:
	@echo "Fujairah Pulse - AI Analysis Platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make demo      - Run the demo version with simulated outputs"
	@echo "  make real      - Run the real version with agentic AI (in development)"
	@echo "  make install   - Install dependencies from requirements.txt"
	@echo "  make clean     - Clean up cache and temporary files"
	@echo ""
	@echo "Quick start:"
	@echo "  make demo      # Start with demo mode immediately"

# Install dependencies
install:
	pip install -r requirements.txt

# Run demo version
demo:
	@echo "Starting Fujairah Pulse in DEMO mode..."
	cd demo && streamlit run app.py --logger.level=warning

# Run real version (development)
real:
	@echo "Starting Fujairah Pulse in REAL mode..."
	@echo "Note: Real analyzer is still in development."
	cd real && streamlit run app.py --logger.level=warning

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "Cleaned up temporary files"
