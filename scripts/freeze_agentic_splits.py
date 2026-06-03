"""Freeze the agentbench + tau2 TRAIN/TEST splits to disk.

Both the WMC and no-WMC arms must iterate identical episodes, so the splits are
frozen once (from the live AgentBench controller / the tau2 registry) and read
back deterministically by the backend data loaders.

File format + path convention (read back by the data loaders):

  AgentBench, one per task in {os, webshop, db, alfworld}:
      data/agentic/<task>_split.json
      {"train": [<idx>, ...], "test": [<idx>, ...]}      # controller indices
      (consumed by worldcalib.agentic.backends.agentbench.data.load_frozen_split)

  tau2, one per domain (telecom by default):
      data/agentic/tau2_<domain>_split.json
      {"train": [<task id>, ...], "test": [<task id>, ...]}
      (consumed by worldcalib.agentic.backends.tau2.data.load_frozen_split)

Indices / ids are written in selection order; the loaders preserve that order.
Defaults: 30 train + 40 test.

AgentBench requires a running controller (the live query). tau2 only needs the
tau2 package importable. The two halves are independent — pass ``--no-agentbench``
or ``--no-tau2`` to skip either.

Run (do NOT run as part of the careful-refactor author step):
    python scripts/freeze_agentic_splits.py \
        --controller-url http://localhost:5020/api
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# Repo root is one level up from scripts/.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_FROZEN_SPLIT_DIR = _REPO_ROOT / "data" / "agentic"

DEFAULT_CONTROLLER_URL = "http://localhost:5020/api"
DEFAULT_TRAIN_SIZE = 30
DEFAULT_TEST_SIZE = 40
DEFAULT_TAU2_DOMAIN = "telecom"

# Author-time default; the agentbench data module owns the canonical tuple.
AGENTBENCH_TASKS: tuple[str, ...] = ("os", "webshop", "db", "alfworld")


def _write_split(path: Path, train: list, test: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"train": train, "test": test}
    path.write_text(json.dumps(payload, indent=2) + "\n")


def freeze_agentbench_task(
    task: str,
    *,
    controller_url: str,
    train_size: int,
    test_size: int,
) -> Path:
    """Query the live controller and freeze one task's index split.

    Imported lazily so the tau2-only path never touches the agentbench module.
    """
    from worldcalib.agentic.backends.agentbench.data import (
        fetch_indices,
        frozen_split_path,
        task_server_name,
    )

    all_idx = fetch_indices(controller_url, task_server_name(task))
    train = all_idx[:train_size]
    test = all_idx[train_size : train_size + test_size]
    path = frozen_split_path(task)
    _write_split(path, train, test)
    return path


def freeze_tau2_domain(
    domain: str,
    *,
    train_size: int,
    test_size: int,
) -> Path:
    """Freeze one tau2 domain's id split from the named train/test splits.

    Imported lazily so the agentbench-only path never imports tau2.
    """
    from worldcalib.agentic.backends.tau2.data import (
        _named_split_ids,
        frozen_split_path,
    )

    train_ids = _named_split_ids(domain, "train") or []
    test_ids = _named_split_ids(domain, "test") or []
    train = list(train_ids[:train_size])
    test = list(test_ids[:test_size])
    path = frozen_split_path(domain)
    _write_split(path, train, test)
    return path


def freeze_all(
    *,
    controller_url: str = DEFAULT_CONTROLLER_URL,
    train_size: int = DEFAULT_TRAIN_SIZE,
    test_size: int = DEFAULT_TEST_SIZE,
    tau2_domain: str = DEFAULT_TAU2_DOMAIN,
    do_agentbench: bool = True,
    do_tau2: bool = True,
    tasks: tuple[str, ...] = AGENTBENCH_TASKS,
) -> list[Path]:
    """Freeze every requested split; returns the written file paths."""
    written: list[Path] = []
    if do_agentbench:
        for task in tasks:
            path = freeze_agentbench_task(
                task,
                controller_url=controller_url,
                train_size=train_size,
                test_size=test_size,
            )
            written.append(path)
            print(f"froze agentbench {task!r} -> {path}")
    if do_tau2:
        path = freeze_tau2_domain(
            tau2_domain,
            train_size=train_size,
            test_size=test_size,
        )
        written.append(path)
        print(f"froze tau2 {tau2_domain!r} -> {path}")
    return written


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--controller-url",
        default=DEFAULT_CONTROLLER_URL,
        help="AgentBench controller base URL (default: %(default)s).",
    )
    parser.add_argument(
        "--train-size",
        type=int,
        default=DEFAULT_TRAIN_SIZE,
        help="Number of train episodes per split (default: %(default)s).",
    )
    parser.add_argument(
        "--test-size",
        type=int,
        default=DEFAULT_TEST_SIZE,
        help="Number of test episodes per split (default: %(default)s).",
    )
    parser.add_argument(
        "--tau2-domain",
        default=DEFAULT_TAU2_DOMAIN,
        help="tau2 domain to freeze (default: %(default)s).",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=list(AGENTBENCH_TASKS),
        help="AgentBench tasks to freeze (default: %(default)s).",
    )
    parser.add_argument(
        "--no-agentbench",
        action="store_true",
        help="Skip the agentbench live query (no controller needed).",
    )
    parser.add_argument(
        "--no-tau2",
        action="store_true",
        help="Skip freezing the tau2 split.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    written = freeze_all(
        controller_url=args.controller_url,
        train_size=args.train_size,
        test_size=args.test_size,
        tau2_domain=args.tau2_domain,
        do_agentbench=not args.no_agentbench,
        do_tau2=not args.no_tau2,
        tasks=tuple(args.tasks),
    )
    print(f"wrote {len(written)} split file(s) under {_FROZEN_SPLIT_DIR}")


if __name__ == "__main__":
    main()
