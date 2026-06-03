"""ARC-AGI-2 task data — train/test splits carried in ``LocomoExample``.

Each ARC-AGI-2 "example" is one task json file: a list of ``train``
demonstration ``{"input": Grid, "output": Grid}`` pairs plus one or more
``test`` entries. To reuse the optimizer main loop without changing its
signatures, every task is wrapped in a ``LocomoExample`` container (mirroring
:func:`worldcalib.agentic.backends.tau2.data._make_example`):

- ``task_id`` / ``sample_id`` = the json file stem (e.g. ``"00576224"``)
- ``question`` / ``answer`` are empty and ``category`` is ``0`` — ARC carries no
  natural-language QA; the grids live in the json file on disk.
- ``metadata`` = ``{"task_path", "task_id", "split", "question_type",
  "num_test"}``.

``question_type`` is the per-category axis for the self-distill prediction
protocol. For ARC it is derived from the *output grid size change* observed
across the visible ``train`` demonstrations — a stable, leak-free signal of the
kind of transformation a task demands (``same_size`` / ``grow`` / ``shrink`` /
``variable``). This is the axis a candidate's upside/downside prediction is
measured against.

Split policy: **both** the ``train`` and ``test`` splits are carved out of the
ARC-AGI-2 repository's ``evaluation`` directory (120 tasks). The 1000-task
``training`` directory is intentionally NOT used — it is far larger than an
optimization run needs and its difficulty distribution differs from the
evaluation set. The 120 evaluation task json files are sorted deterministically
by filename and partitioned by ordinal position (see
:data:`ARC_TRAIN_PARTITION_SIZE`): the **first 30** files are the ``train``
split and the **remaining 90** are the ``test`` split. The partition is a pure,
documented ordinal slice (filename order), so it is reproducible without any
frozen id list. Only the file *path* is stored on the example — the gold test
outputs are deliberately NOT loaded here so the evaluation runner can withhold
them from the scaffold.
"""

from __future__ import annotations

import json
from pathlib import Path

from worldcalib.schemas import LocomoExample

ARC_DEFAULT_DATA_DIR = Path("/data/home/yuhan/ARC-AGI-2/data")

# Both splits come from the ``evaluation`` directory (120 tasks), sorted by
# filename. The first ``ARC_TRAIN_PARTITION_SIZE`` files are the ``train`` split;
# the rest are the ``test`` split. This is a pure ordinal slice — deterministic
# and reproducible without a frozen id list.
ARC_EVAL_SUBDIR = "evaluation"
ARC_TRAIN_PARTITION_SIZE = 30


def task_question_type(train_pairs: list[dict]) -> str:
    """Per-category label for a task: the output grid size change axis.

    Derived from the visible ``train`` demonstrations (stable / leak-free). For
    each demonstration pair the output grid *area* (``rows * cols``) is compared
    against the input grid area:

    - all outputs equal their input        -> ``"same_size"``
    - all outputs strictly larger          -> ``"grow"``
    - all outputs strictly smaller         -> ``"shrink"``
    - mixed directions (or no usable pairs) -> ``"variable"``
    """
    relations: list[str] = []
    for pair in train_pairs:
        inp = pair.get("input")
        out = pair.get("output")
        if not inp or not out:
            continue
        in_area = len(inp) * len(inp[0]) if inp and inp[0] is not None else len(inp)
        out_area = len(out) * len(out[0]) if out and out[0] is not None else len(out)
        if out_area == in_area:
            relations.append("same_size")
        elif out_area > in_area:
            relations.append("grow")
        else:
            relations.append("shrink")

    if not relations:
        return "variable"
    unique = set(relations)
    if len(unique) == 1:
        return relations[0]
    return "variable"


def _partition_eval_files(data_dir: Path, split: str) -> list[Path]:
    """Return the ordered eval-dir task files belonging to ``split``.

    The ``evaluation`` directory's json files are sorted by filename. The first
    :data:`ARC_TRAIN_PARTITION_SIZE` files form the ``train`` partition; the rest
    form the ``test`` partition. Any other ``split`` value returns the whole
    evaluation directory (train partition followed by test partition).
    """
    eval_dir = data_dir / ARC_EVAL_SUBDIR
    files = sorted(eval_dir.glob("*.json"), key=lambda p: p.name)
    if split == "train":
        return files[:ARC_TRAIN_PARTITION_SIZE]
    if split == "test":
        return files[ARC_TRAIN_PARTITION_SIZE:]
    return files


def _make_example(task_path: Path, task: dict, split: str) -> LocomoExample:
    stem = task_path.stem
    metadata: dict[str, object] = {
        "task_path": str(task_path.resolve()),
        "task_id": stem,
        "split": split,
        "question_type": task_question_type(task.get("train", [])),
        "num_test": len(task.get("test", [])),
    }
    return LocomoExample(
        task_id=stem,
        sample_id=stem,
        question="",
        answer="",
        category=0,
        evidence=(),
        conversation=(),
        metadata=metadata,
    )


def load_arc_examples(
    data_dir: str | Path,
    split: str,
    *,
    train_size: int,
    test_size: int,
    limit: int = 0,
) -> list[LocomoExample]:
    """Load ARC-AGI-2 tasks for a split as ``LocomoExample`` containers.

    Both splits are carved from ``{data_dir}/evaluation`` (sorted by filename):
    ``split`` ``"train"`` is the first :data:`ARC_TRAIN_PARTITION_SIZE` (30)
    files, ``"test"`` is the remaining 90, and anything else returns the whole
    evaluation directory (train partition then test partition). The partition is
    a pure ordinal slice, so it is deterministic and reproducible.

    Within the selected partition the count is capped: ``train_size`` for the
    ``train`` split, ``test_size`` for the ``test`` split (the larger
    ``train_size`` cap is applied to the combined listing for any other split).
    ``limit`` then caps the length of the returned list. Only the task path (not
    the gold test outputs) is stored on each example — the runner reloads the
    json and withholds gold.
    """
    base = Path(data_dir)
    selected = _partition_eval_files(base, split)

    cap = test_size if split == "test" else train_size
    if cap:
        selected = selected[:cap]

    if limit:
        selected = selected[:limit]

    examples: list[LocomoExample] = []
    for task_path in selected:
        with task_path.open("r", encoding="utf-8") as handle:
            task = json.load(handle)
        examples.append(_make_example(task_path, task, split))
    return examples
