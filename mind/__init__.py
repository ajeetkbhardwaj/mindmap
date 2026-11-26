"""DeepWiki API package.

mind/api is kept unchanged and uses absolute ``api.*`` imports internally.
Adding this package's directory to ``sys.path`` lets those imports resolve
both as ``api.*`` (internal) and as ``mind.api.*`` (external), so the whole
repository can ship as one installable package.
"""
import sys
from pathlib import Path

_MIND_DIR = str(Path(__file__).parent)
if _MIND_DIR not in sys.path:
    sys.path.insert(0, _MIND_DIR)

__version__ = "1.0.0"
