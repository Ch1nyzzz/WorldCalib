"""Helpers for working with vendored upstream memory systems."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from worldcalib.paths import runtime_root



def vendor_path(name: str, *, root: Path | None = None) -> Path:
    """Return the checked-out reference repository path."""

    vendor_root = root or (runtime_root() / "references" / "vendor")
    return Path(vendor_root).expanduser().resolve() / name


@contextmanager
def prepend_sys_path(path: Path) -> Iterator[None]:
    """Temporarily prepend a path for upstream imports."""

    text = str(path)
    inserted = False
    if text not in sys.path:
        sys.path.insert(0, text)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(text)
            except ValueError:
                pass
