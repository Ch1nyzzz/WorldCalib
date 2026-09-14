"""Read measured task outcomes; no prediction grading or belief taxonomy."""

import json
from pathlib import Path


def _iter_task_rows(result_path: Path):
    """Yield ``(task_id, passed, score)`` for every row in a result's tasks[].

    With multi-run evaluation (``runs >= 2``) the same task_id appears once per
    run; callers aggregate.
    """
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for t in d.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = t.get("task_id") or t.get("id") or t.get("question_id")
        if tid is None:
            continue
        score = t.get("score")
        passed = t.get("passed")
        if passed is None:
            passed = score is not None and float(score) > 0
        yield str(tid), bool(passed), (float(score) if score is not None else None)


def load_task_outcomes(result_path: Path) -> dict[str, bool]:
    """Read a candidate_results/*.json and return ``{task_id: passed}``.

    Only STABLE tasks are returned: with multi-run evaluation a task whose runs
    disagree (e.g. 1/2 passed) is noise, not signal — it is dropped here so the
    evidence consumer can distinguish repeatable outcomes from noise. Single-run results are
    unaffected (every task is trivially stable).
    """
    runs_by_task: dict[str, list[bool]] = {}
    for tid, passed, _ in _iter_task_rows(result_path):
        runs_by_task.setdefault(tid, []).append(passed)
    return {
        tid: runs[0]
        for tid, runs in runs_by_task.items()
        if all(r == runs[0] for r in runs)
    }


def load_task_pass_runs(result_path: Path) -> dict[str, list[bool]]:
    """Per-task pass outcome of every run: ``{task_id: [passed, ...]}``.

    The unstable tasks (mixed True/False) that :func:`load_task_outcomes`
    drops are visible here for callers that want to report them.
    """
    runs_by_task: dict[str, list[bool]] = {}
    for tid, passed, _ in _iter_task_rows(result_path):
        runs_by_task.setdefault(tid, []).append(passed)
    return runs_by_task


def load_task_scores(result_path: Path) -> dict[str, float]:
    """Mean score per task across runs: ``{task_id: mean_score}``."""
    scores_by_task: dict[str, list[float]] = {}
    for tid, _, score in _iter_task_rows(result_path):
        if score is not None:
            scores_by_task.setdefault(tid, []).append(score)
    return {tid: sum(s) / len(s) for tid, s in scores_by_task.items()}


def load_score_breakdown(result_path: Path) -> dict:
    """Read a candidate_results/*.json and return its ``score_breakdown``.

    Used with raw task scores to build the shared score-history evidence.
    """
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d.get("score_breakdown") or {}
