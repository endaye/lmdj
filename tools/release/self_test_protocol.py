"""One module identity for the shared producer/consumer protocol, not target code."""
from pathlib import Path
import sys

_CI_MODULES = Path(__file__).resolve().parents[2] / "scripts/ci"
if str(_CI_MODULES) not in sys.path:
    sys.path.insert(0, str(_CI_MODULES))

import self_test as protocol
from self_test_evidence import SelfTestEvidenceError, validate_verdict_document

__all__ = ["protocol", "SelfTestEvidenceError", "validate_verdict_document"]
