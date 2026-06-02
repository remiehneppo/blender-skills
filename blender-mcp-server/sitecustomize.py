from __future__ import annotations

"""Make the checkout importable without an editable install."""

from pathlib import Path
import sys


def _add_src_to_path() -> None:
    root = Path(__file__).resolve().parent
    src = root / "src"
    if src.is_dir():
        src_str = str(src)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


_add_src_to_path()
