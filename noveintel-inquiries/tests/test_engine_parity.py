"""
Parity with the application this was ported from.

The safety net for the port (porting guide §3): the vendored stages must behave
exactly as the originals did on real input. The stages themselves were copied
unchanged, so what is actually at risk is everything around them — the path fixes, the
branding seam, the ``include_english`` gate — and that is what these check.

Skipped when the legacy checkout is not present. A deployed service has no ``real/``
directory, and a parity test with nothing to compare against has nothing to say.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from noveintel_inquiries.api.models import records_to_frame


def _load_legacy(legacy_root: Path, module: str):
    """Import one legacy stage module as part of its own package.

    As a package member, not by file path: the stages use relative imports
    (``from .state import PipelineState``), and a module loaded by path has no parent
    package for those to resolve against.

    The ``legacy_root`` fixture has already put the flow directory on ``sys.path``,
    which makes its ``pipeline/`` directory importable as a top-level package. That
    name does not collide with ``noveintel_inquiries.pipeline``, which is a submodule of an
    installed package and lives in a different namespace.
    """
    if not (legacy_root / "pipeline" / f"{module}.py").is_file():
        pytest.skip(f"The legacy {module} is not in this checkout.")
    try:
        return importlib.import_module(f"pipeline.{module}")
    except ImportError as exc:
        pytest.skip(f"The legacy {module} could not be imported here: {exc}")


class TestStage1Parity:
    def test_the_column_contract_has_not_drifted(self, legacy_root):
        """The required and optional column lists are the contract ``records.py``
        encodes. If the legacy flow changes them, this contract is now wrong."""
        legacy = _load_legacy(legacy_root, "stage1_validator")
        from noveintel_inquiries.stages import stage1_validator as ported

        assert ported.REQUIRED_COLUMNS == legacy.REQUIRED_COLUMNS
        assert ported.OPTIONAL_COLUMNS == legacy.OPTIONAL_COLUMNS
        assert ported.COLUMN_MAPPING == legacy.COLUMN_MAPPING

    def test_the_request_model_covers_every_contract_column(self):
        """Every column stage 1 knows about must be reachable from the API, or a
        tenant has data the service cannot accept."""
        from noveintel_inquiries.api.models import InquiryRecord
        from noveintel_inquiries.stages import stage1_validator as ported

        aliases = {
            field.alias for field in InquiryRecord.model_fields.values() if field.alias
        }
        contract = set(ported.REQUIRED_COLUMNS) | set(ported.OPTIONAL_COLUMNS)
        assert contract <= aliases, sorted(contract - aliases)

    def test_validation_agrees_on_a_real_payload(self, legacy_root, analysis_request):
        """The ported stage 1 and the legacy one must reach the same verdict."""
        legacy = _load_legacy(legacy_root, "stage1_validator")
        from noveintel_inquiries.stages.stage1_validator import run_stage1 as ported_run
        from noveintel_inquiries.stages.state import PipelineState as PortedState

        frame = records_to_frame(analysis_request.records)
        ported_state = ported_run(PortedState(), frame.copy())
        legacy_state = legacy.run_stage1(legacy.PipelineState(), frame.copy())

        assert ported_state.total_cases == legacy_state.total_cases
        assert list(ported_state.original_columns) == list(legacy_state.original_columns)


class TestVendoringIntegrity:
    def test_the_stages_were_copied_not_rewritten(self, legacy_root):
        """The analysis is the thing under parity test, so it must not have drifted.

        Only the files this port deliberately changed are exempt, and each exemption
        is named — an unexplained difference in any other stage means the port
        silently altered the analysis.

        Line endings are not a difference. With ``core.autocrlf=true`` a Windows
        checkout writes CRLF, and whether the two copies match then depends on how
        each was checked out, not on what they say.
        """
        changed = {
            "llm.py",              # relative import in place of a sys.path insertion
            "orchestrator.py",     # vendored guidebook path, include_english
            "stage6_artifacts.py", # branding injection, include_english gate
            "stage6_json_report.py",  # stable chart keys
            "state.py",            # the branding field
            "translate_report_en.py",  # re-key translated table rows (empty English tables)
            "build_report_ar.py",  # vendored word builder, per-run logo
            "build_report_en.py",  # vendored word builder, per-run logo
        }
        ported_dir = Path(
            importlib.util.find_spec("noveintel_inquiries.stages").submodule_search_locations[0]
        )
        legacy_dir = legacy_root / "pipeline"

        drifted = []
        for ported in sorted(ported_dir.glob("*.py")):
            if ported.name in changed:
                continue
            original = legacy_dir / ported.name
            if not original.is_file():
                drifted.append(f"{ported.name}: not in the legacy flow")
            elif _lf(ported.read_bytes()) != _lf(original.read_bytes()):
                drifted.append(f"{ported.name}: differs from the legacy flow")
        assert not drifted, drifted


def _lf(data: bytes) -> bytes:
    """A file's bytes with CRLF line endings normalised to LF."""
    return data.replace(b"\r\n", b"\n")
