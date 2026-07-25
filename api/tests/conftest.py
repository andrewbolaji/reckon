"""The API image builds from api/ alone, so tests import main.py the same way."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
