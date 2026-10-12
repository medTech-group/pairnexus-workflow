#!/usr/bin/env python3
"""Entry point for the kit's `workflow` command (see scripts/workflow/cli.py)."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("workflow needs Python 3.11 or newer (for tomllib)")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
