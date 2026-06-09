"""Classify a designer checkpoint's change as prompt-level vs code-level.

The designer's hard floor is "≥3 *completely different* directions", and a
prompt-wording or temperature tweak does NOT count as a direction. This module
gives the goal-loop a cheap, deterministic *hint* (the model judge makes the
final call): does a checkpoint's edited ``terminus_2`` package differ from the
baseline only in prompt surface (template text + the ``temperature`` /
``parser_name`` / ``max_turns`` knobs / ``agent_kwargs``), or does it change
actual control-flow code?

Layout (see ``references/vendor/terminus2_agent/terminus_2/``):
  templates/*.txt              -> prompt surface (template text)
  *.py  (terminus_2.py, ...)   -> code; but a diff that only edits the prompt
                                  knobs above is still prompt-level.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

# Lines that, even inside a .py file, are "prompt knobs" rather than control flow.
_PROMPT_KNOB_RE = re.compile(
    r"\b(temperature|parser_name|max_turns|max_episodes|suppress_max_turns_warning)\b"
)
# Structural tokens that mark a changed .py line as genuine code (control flow,
# new functions/classes, calls, awaits, returns, imports, state mutation).
_CODE_TOKEN_RE = re.compile(
    r"(^\s*(def |class |async |await |if |elif |else|for |while |with |try|except|finally|return|yield|raise|import |from )"
    r"|self\.\w+\s*=|\.\w+\(|=\s*\w+\()"
)

_IGNORE = ("__pycache__", ".pyc")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _rel_files(root: Path) -> dict[str, Path]:
    """All terminus_2 package files under `root`, keyed by package-relative path."""
    pkg = root / "terminus_2"
    base = pkg if pkg.is_dir() else root
    out: dict[str, Path] = {}
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if any(tok in str(p) for tok in _IGNORE):
            continue
        out[str(p.relative_to(base)).replace("\\", "/")] = p
    return out


def _changed_py_lines(old: str, new: str) -> list[str]:
    """The added/removed lines of a unified diff (the '+'/'-' body lines)."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")
    out: list[str] = []
    for line in diff:
        if line[:3] in ("---", "+++", "@@ ") or line.startswith("@@"):
            continue
        if line and line[0] in "+-":
            out.append(line[1:])
    return out


def _py_change_is_code(old: str, new: str) -> tuple[bool, list[str]]:
    """True if a .py file's diff touches control-flow code (not just prompt knobs
    or docstring/string text). Returns (is_code, sample_changed_lines)."""
    changed = [ln for ln in _changed_py_lines(old, new) if ln.strip()]
    code_lines = [
        ln
        for ln in changed
        if _CODE_TOKEN_RE.search(ln) and not _PROMPT_KNOB_RE.search(ln)
    ]
    return (len(code_lines) > 0, changed[:8])


def classify_change(baseline_root: Path, candidate_root: Path) -> dict:
    """Classify candidate vs baseline. Returns a dict with:

    ``class``: ``"code-level"`` | ``"prompt-level"`` | ``"none"``
    ``changed_files``: sorted list of package-relative paths that differ
    ``code_files`` / ``prompt_files``: split of changed files
    ``evidence``: {file: [sample changed lines]} for the code files
    """

    base = _rel_files(Path(baseline_root))
    cand = _rel_files(Path(candidate_root))
    all_rel = sorted(set(base) | set(cand))

    changed: list[str] = []
    code_files: list[str] = []
    prompt_files: list[str] = []
    evidence: dict[str, list[str]] = {}

    for rel in all_rel:
        old = _read(base[rel]) if rel in base else ""
        new = _read(cand[rel]) if rel in cand else ""
        if old == new:
            continue
        changed.append(rel)
        is_new_or_removed = (rel not in base) or (rel not in cand)
        if rel.endswith(".txt") or "templates/" in rel:
            prompt_files.append(rel)  # template text == prompt surface
        elif rel.endswith(".py"):
            # A brand-new or deleted .py module is structural by definition.
            if is_new_or_removed:
                code_files.append(rel)
                evidence[rel] = ["(new/removed module)"]
            else:
                is_code, sample = _py_change_is_code(old, new)
                (code_files if is_code else prompt_files).append(rel)
                if is_code:
                    evidence[rel] = sample
        else:
            code_files.append(rel)  # other assets (shell, etc.) — treat as code

    if not changed:
        cls = "none"
    elif code_files:
        cls = "code-level"
    else:
        cls = "prompt-level"

    return {
        "class": cls,
        "changed_files": changed,
        "code_files": code_files,
        "prompt_files": prompt_files,
        "evidence": evidence,
    }
