#!/usr/bin/env python3
"""In-sandbox `worldcalib-check` — a FREE, instant correctness gate.

Designer evals are slow (~15-60 min). A syntax/import break in your edited
terminus_2 package makes EVERY task fail, so paying a real eval just to discover
a typo is a waste. Run this first — it byte-compiles and imports your edited
package locally (no harbor, no cost) and reports any error.

Usage (from the workspace root):
    python .worldcalib_tools/check.py
    python .worldcalib_tools/check.py --source terminus2_agent

Exit 0 = loads clean (safe to eval). Non-zero = fix the reported error first.
Pure stdlib.
"""

from __future__ import annotations

import argparse
import compileall
import io
import os
import sys
import traceback
from contextlib import redirect_stdout

DEFAULT_SOURCE_REL = "terminus2_agent"
EVAL_REQUEST_DIR = "eval_requests"  # workspace-root marker (created by the bridge)


def find_workspace_root(start: str) -> str:
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, EVAL_REQUEST_DIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Free syntax+import gate for the edited agent.")
    ap.add_argument("--source", default=DEFAULT_SOURCE_REL,
                    help="terminus-2 source root (parent of the terminus_2 package).")
    args = ap.parse_args()

    workspace = find_workspace_root(os.getcwd())
    source_root = (
        args.source if os.path.isabs(args.source)
        else os.path.join(workspace, args.source)
    )
    pkg_dir = os.path.join(source_root, "terminus_2")
    entry = os.path.join(pkg_dir, "terminus_2.py")

    if not os.path.isfile(entry):
        print(f"FAIL: {entry} not found — is --source pointing at the package root?")
        return 2

    # 1) byte-compile the whole package (catches syntax errors fast).
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = compileall.compile_dir(pkg_dir, quiet=1, force=True)
    if not ok:
        print("FAIL: syntax error during byte-compile:")
        print(buf.getvalue()[-2000:])
        return 1

    # 2) import the entry module so import-time errors surface (missing symbol,
    #    bad relative import, NameError at module scope, ...).
    sys.path.insert(0, source_root)
    for mod in [m for m in list(sys.modules) if m.startswith("terminus_2")]:
        del sys.modules[mod]
    try:
        import importlib
        m = importlib.import_module("terminus_2.terminus_2")
        if not hasattr(m, "Terminus2"):
            print("FAIL: module imported but class `Terminus2` is missing "
                  "(the BaseAgent entry class must stay named Terminus2).")
            return 1
    except Exception:  # noqa: BLE001 - report any import-time failure
        print("FAIL: import error:")
        print(traceback.format_exc()[-2000:])
        return 1

    print("OK: terminus_2 package byte-compiles and imports; class Terminus2 present.")
    print("(This is a free local check — it does NOT run any task. Eval to get scores.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
