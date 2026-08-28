"""Make the bundle's `src` tree importable without an install step.

Bundles must run under a bare `python -m pytest` in a minimal image, so there is no editable
install and no packaging metadata to depend on.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
