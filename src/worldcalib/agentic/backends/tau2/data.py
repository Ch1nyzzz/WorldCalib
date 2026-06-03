"""tau2 task data — train/test splits carried in ``LocomoExample``.

Each tau2 "example" is one ``(domain, task_id)`` episode. To reuse the optimizer
main loop without changing its signatures, every example is wrapped in a
``LocomoExample`` container:

- ``task_id`` / ``sample_id`` = ``f"{domain}#{task.id}"``
- ``metadata`` = ``{"domain", "task_id", "split", "question_type"}``

``question_type`` is the per-category axis for the self-distill prediction
protocol. For tau2 it is derived from the task's ``reward_basis`` — the set of
checks the task is graded on (e.g. ``ENV_ASSERTION``, ``DB+COMMUNICATE``,
``NL_ASSERTION``). This groups tasks by *what kind of correctness* they demand,
which is the axis a candidate's upside/downside prediction is measured against.

Splits use tau2's own named splits when the domain registers them
(``registry.get_task_splits_loader(domain)`` — telecom/airline/retail ship
``train``/``test``). Domains without named splits fall back to a deterministic
ordinal slice over the task list.

``tau2`` is imported here (this module is part of the tau2 backend).

Frozen splits: an optional ``data/agentic/tau2_<domain>_split.json`` carrying
``{"train": [...task ids], "test": [...task ids]}`` makes the train/test ids
fully reproducible across the WMC / no-WMC arms. When the frozen file is absent,
the effective default is deterministic: the front ``train_size`` ids of tau2's
named ``train`` split and the named ``test`` split (or an ordinal slice for
domains without named splits).
"""

from __future__ import annotations

import json
from pathlib import Path

from tau2.registry import registry

from worldcalib.schemas import LocomoExample

TAU2_DOMAINS: tuple[str, ...] = ("telecom", "airline", "retail")

# Frozen id splits live alongside the agentbench ones:
#   data/agentic/tau2_<domain>_split.json -> {"train": [...ids], "test": [...ids]}
# The repo root is six levels up from this file
# (tau2/backends/agentic/worldcalib/src/worldcalib).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_FROZEN_SPLIT_DIR = _REPO_ROOT / "data" / "agentic"


def task_question_type(task: object) -> str:
    """Per-category label for a task: a signature of its ``reward_basis``."""
    criteria = getattr(task, "evaluation_criteria", None)
    reward_basis = getattr(criteria, "reward_basis", None) if criteria else None
    if not reward_basis:
        return "all"
    labels = sorted(getattr(rt, "value", str(rt)) for rt in reward_basis)
    return "+".join(labels) if labels else "all"


def _make_example(domain: str, task: object, split: str) -> LocomoExample:
    metadata: dict[str, object] = {
        "domain": domain,
        "task_id": task.id,
        "split": split,
        "question_type": task_question_type(task),
    }
    return LocomoExample(
        task_id=f"{domain}#{task.id}",
        sample_id=f"{domain}#{task.id}",
        question="",
        answer="",
        category=0,
        evidence=(),
        conversation=(),
        metadata=metadata,
    )


def frozen_split_path(domain: str) -> Path:
    """Path to the frozen tau2 id-split file for a domain (may not exist)."""
    return _FROZEN_SPLIT_DIR / f"tau2_{domain}_split.json"


def load_frozen_split(domain: str) -> dict[str, list[str]] | None:
    """Frozen ``{"train": [...ids], "test": [...ids]}`` id split, or None if absent.

    Ids are returned in their on-disk order (deterministic, frozen at freeze
    time) so both the WMC and no-WMC arms iterate identical episodes.
    """
    path = frozen_split_path(domain)
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return {
        "train": [str(i) for i in payload.get("train", [])],
        "test": [str(i) for i in payload.get("test", [])],
    }


def _named_split_ids(domain: str, split: str) -> list[str] | None:
    """Task ids for a domain's registered named split, or None if unavailable."""
    try:
        loader = registry.get_task_splits_loader(domain)
    except Exception:
        return None
    if loader is None:
        return None
    try:
        splits = loader()
    except Exception:
        return None
    ids = splits.get(split)
    return list(ids) if ids else None


def load_tau2_examples(
    domain: str,
    split: str,
    *,
    train_size: int,
    test_size: int,
    limit: int = 0,
) -> list[LocomoExample]:
    """Deterministic train/test split over a domain's tasks.

    Resolution order (most to least preferred), all deterministic:

    1. Frozen id split at ``data/agentic/tau2_<domain>_split.json``.
    2. tau2's registered named splits (``train``/``test``). The named ``train``
       split is deterministically truncated to the front ``train_size`` ids and
       the named ``test`` split to the front ``test_size`` ids, so the effective
       default (telecom: 30 train / 40 test) is fully reproducible.
    3. Ordinal slice over the task list for domains without named splits.
    """
    all_tasks = list(registry.get_tasks_loader(domain)())
    by_id = {t.id: t for t in all_tasks}

    if split in ("train", "test"):
        size = train_size if split == "train" else test_size
        frozen = load_frozen_split(domain)
        if frozen is not None:
            selected = [by_id[i] for i in frozen[split] if i in by_id]
        else:
            named = _named_split_ids(domain, split)
            if named is not None:
                ordered = [by_id[i] for i in named if i in by_id]
                selected = ordered[:size] if size else ordered
            elif split == "train":
                selected = all_tasks[:train_size]
            else:
                selected = all_tasks[train_size : train_size + test_size]
    else:
        selected = all_tasks

    if limit:
        selected = selected[:limit]

    return [_make_example(domain, t, split) for t in selected]
