#!/usr/bin/env bash
# Stop hook: block finishing while the ingest unit tests fail.
#
# This is the gate behind "tests pass" in the definition of done. Claude Code
# runs it every time the assistant tries to stop. It runs the same tests as
# `make test` (ingest/tests, fast and database free). On failure it exits 2,
# which blocks the stop and feeds the failure back so the work continues.
#
# It prefers the project virtualenv (.venv) so it works without an activated
# shell, and falls back to python3 / python. If tests cannot run at all (deps
# missing), that is treated as failing, which is the correct signal.
set -uo pipefail

# Drain and ignore the hook stdin JSON (fields like stop_hook_active are unused;
# the gate is the test result itself, so it can never loop once tests pass).
cat >/dev/null 2>&1 || true

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$root" || exit 0

if [ -x ".venv/bin/python" ]; then
  py=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  py="python"
else
  py="python3"
fi

output="$("$py" -m pytest ingest/tests/ -q 2>&1)"
code=$?

if [ "$code" -ne 0 ]; then
  {
    echo "Stop blocked: ingest tests are failing (the same suite as 'make test')."
    echo "Fix them before finishing. Last lines:"
    echo "$output" | tail -20
  } >&2
  exit 2
fi

exit 0
