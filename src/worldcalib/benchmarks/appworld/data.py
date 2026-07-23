"""Paper-aligned AppWorld scenario-disjoint task split."""

from __future__ import annotations

from worldcalib.paths import package_json
from worldcalib.schemas import LocomoExample


PAPER_TRAIN_SIZE = 45
PAPER_TEST_SIZE = 372


def load_split_ids(split: str) -> list[str]:
    """Load the 45-train / 372-test split bundled with WorldCalib."""

    if split not in {"train", "test"}:
        raise ValueError(f"AppWorld split must be 'train' or 'test', got {split!r}")
    challenge = package_json(
        "worldcalib.benchmarks.appworld", "split_challenge.json"
    )
    challenge_ext = package_json(
        "worldcalib.benchmarks.appworld", "split_challenge_ext.json"
    )
    train = [str(task_id) for task_id in challenge["train"]]
    ext_train = [str(task_id) for task_id in challenge_ext["train"]]
    if train != ext_train:
        raise ValueError("AppWorld challenge and challenge_ext train IDs disagree")
    test = [str(task_id) for task_id in challenge["test"]]
    test.extend(str(task_id) for task_id in challenge_ext["test"])
    if len(train) != PAPER_TRAIN_SIZE or len(test) != PAPER_TEST_SIZE:
        raise ValueError(
            f"invalid AppWorld paper split: train={len(train)}, test={len(test)}"
        )
    if len(set(train)) != len(train) or len(set(test)) != len(test):
        raise ValueError("AppWorld split contains duplicate task IDs")
    if set(train) & set(test):
        raise ValueError("AppWorld train and test task IDs overlap")
    return train if split == "train" else test


def load_appworld_examples(split: str = "train", *, limit: int = 0) -> list[LocomoExample]:
    """Represent AppWorld task IDs using the shared evaluation schema."""

    ids = load_split_ids(split)
    if limit:
        ids = ids[:limit]
    return [
        LocomoExample(
            task_id=f"appworld#{task_id}",
            sample_id=task_id,
            question=task_id,
            answer="",
            category=0,
            evidence=(),
            conversation=(),
            metadata={
                "benchmark": "appworld",
                "split": split,
                "question_type": "all",
                "appworld_task_id": task_id,
            },
        )
        for task_id in ids
    ]


__all__ = [
    "PAPER_TEST_SIZE",
    "PAPER_TRAIN_SIZE",
    "load_appworld_examples",
    "load_split_ids",
]
