"""Local conftest for layout_exporter integration tests.

Adds the test directory to ``sys.path`` so sibling test modules can
import ``_helpers`` directly. Needed because pytest's importlib mode
does not fully register parent test packages, which breaks relative
imports under older pytest versions used in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
