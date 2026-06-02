#!/usr/bin/env python3
"""Quick test to verify the complaint table count fix works."""

import sys
import os
from pathlib import Path
import importlib.util

# Add paths
real_path = Path(__file__).parent / "real"
sys.path.insert(0, str(real_path))
sys.path.insert(0, str(Path(__file__).parent))

# Load orchestrator directly (package has dashes in name which can't be imported normally)
orchestrator_path = real_path / "complaints-flow" / "pipeline" / "orchestrator.py"
spec = importlib.util.spec_from_file_location("orchestrator_module", orchestrator_path)
orchestrator_module = importlib.util.module_from_spec(spec)

# Set up import path before loading
os.chdir(str(real_path))
sys.path.insert(0, str(real_path / "complaints-flow" / "pipeline"))

# Now load the module
try:
    spec.loader.exec_module(orchestrator_module)
    run_full_pipeline = orchestrator_module.run_full_pipeline
except Exception as e:
    print(f"Failed to load orchestrator: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def main():
    input_file = Path("/Users/lena/Downloads/Complaints 2025_50_rows.xlsx")

    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return 1

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        return 1

    print("=" * 60)
    print("RUNNING FULL PIPELINE TEST")
    print(f"Input: {input_file}")
    print("=" * 60)

    try:
        success, message, state, report = run_full_pipeline(str(input_file), api_key)

        if success:
            print("\n✓ PIPELINE PASSED")
            print(f"  Total cases: {state.total_cases}")
            print(f"  All classified: {len(state.all_classified)}")
            complaint_count = len([c for c in state.all_classified if c.actual_contact_type == "شكوى"])
            print(f"  Complaints: {complaint_count}")

            if report and "sections" in report:
                for section in report.get("sections", []):
                    print(f"  ✓ Section: {section.get('heading', 'Unknown')}")

            return 0
        else:
            print(f"\n✗ PIPELINE FAILED")
            print(f"  Error: {message}")
            return 1

    except Exception as e:
        print(f"\n✗ EXCEPTION OCCURRED")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
