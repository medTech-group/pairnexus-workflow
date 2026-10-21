#!/usr/bin/env python3
"""Entry point for the kit's `workflow` command (see scripts/workflow/cli.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.version_info < (3, 11):
    # The kit needs tomllib. An old Python's hooks still fail closed (#22), and
    # `doctor` gives a short report (#61).
    from workflow import _old_python

    sys.exit(_old_python.main(sys.argv[1:]))

from workflow.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
