"""Structured audit logger for copilot tool calls."""

import json
import os
import sys
from datetime import datetime, timezone


def _log_file():
    path = os.getenv("COPILOT_AUDIT_LOG")
    if path:
        return open(path, "a")
    return None


def log_entry(entry: dict) -> None:
    """Write a JSON audit line to stderr and optionally to a file."""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(entry, default=str)

    print(line, file=sys.stderr)

    f = _log_file()
    if f:
        try:
            f.write(line + "\n")
        finally:
            f.close()
