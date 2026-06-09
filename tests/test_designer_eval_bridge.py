"""Unit tests for the AutoLab designer eval bridge (no harbor).

We inject a fake runner so the protocol — request pickup, free task choice,
per-task flip vs the baseline, task-run budget, and checkpoint freezing — is
exercised without shelling out to harbor.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from worldcalib.autolab.autolab import AutolabTask
from worldcalib.autolab.eval_bridge import (
    EVAL_REQUEST_DIR,
    EVAL_RESULT_DIR,
    CHECKPOINT_REQUEST_DIR,
    CHECKPOINT_RESULT_DIR,
    DesignerBudget,
    EvalBridge,
)
from worldcalib.schemas import CandidateResult


def _make_source(root: Path) -> Path:
    pkg = root / "terminus2_agent" / "terminus_2"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "terminus_2.py").write_text("class Terminus2:\n    pass\n", encoding="utf-8")
    return root / "terminus2_agent"


class _FakeRunner:
    """Mimics AutolabHarborRunner: emits one row per requested task. Only `t1`
    passes (so vs an all-fail baseline it is the single fail->pass flip)."""

    def __init__(self, out_dir: Path, tasks: list[AutolabTask], n_attempts: int = 1,
                 seen_attempts: list | None = None) -> None:
        self.out_dir = Path(out_dir)
        self.tasks = tasks
        self.n_attempts = n_attempts
        if seen_attempts is not None:
            seen_attempts.append(n_attempts)

    def evaluate_candidate(self, *, candidate, candidate_id, **_):
        rows = []
        for t in self.tasks:
            # mimic harbor's per-task job dir + trajectory log
            jobs_dir = self.out_dir / "agent_runs" / candidate_id / t.task_id / "job"
            jobs_dir.mkdir(parents=True, exist_ok=True)
            (jobs_dir / "job.log").write_text(
                f"trajectory for {t.task_id}: did stuff\n", encoding="utf-8"
            )
            rows.append(
                {
                    "task_id": t.task_id,
                    "score": 0.8 if t.task_id == "t1" else 0.2,
                    "passed": t.task_id == "t1",
                    "metadata": {"jobs_dir": str(jobs_dir)},
                }
            )
        results_dir = self.out_dir / "candidate_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        result_path = results_dir / f"{candidate_id}.json"
        result_path.write_text(
            json.dumps({"candidate": {}, "tasks": rows}), encoding="utf-8"
        )
        n = len(rows)
        return CandidateResult(
            candidate_id=candidate_id,
            scaffold_name="terminus2_autolab",
            passrate=sum(r["passed"] for r in rows) / n if n else 0.0,
            average_score=0.5,
            token_consuming=0,
            avg_token_consuming=0.0,
            avg_prompt_tokens=0.0,
            avg_completion_tokens=0.0,
            count=n,
            config=dict(candidate),
            result_path=str(result_path),
        )


def _train_tasks() -> list[AutolabTask]:
    return [
        AutolabTask(task_id="t1", instruction="i1", path=Path("/tmp/t1")),
        AutolabTask(task_id="t2", instruction="i2", path=Path("/tmp/t2")),
        AutolabTask(task_id="t3", instruction="i3", path=Path("/tmp/t3")),
    ]


def _submit(workspace: Path, sub_dir: str, req_id: str, payload: dict) -> None:
    d = workspace / sub_dir
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{req_id}.json.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(d / f"{req_id}.json")


def _await_result(workspace: Path, sub_dir: str, req_id: str, timeout: float = 8.0) -> dict:
    path = workspace / sub_dir / f"{req_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError(f"no result at {path} within {timeout}s")


def _make_bridge(tmp_path, budget: DesignerBudget):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_source(ws)  # ws/terminus2_agent/terminus_2/terminus_2.py
    # pristine baseline copy for diff classification
    baseline = tmp_path / "baseline"
    _make_source(baseline)
    events: list[dict] = []
    seen_attempts: list[int] = []
    br = EvalBridge(
        workspace=ws,
        out_dir=tmp_path / "designer",
        runner_factory=(
            lambda tasks, out, n_attempts=1: _FakeRunner(
                out, tasks, n_attempts or 1, seen_attempts
            )
        ),
        train_tasks=_train_tasks(),
        base_outcomes={"t1": False, "t2": False, "t3": False},
        budget=budget,
        baseline_source=baseline / "terminus2_agent",
        smoke_size=3,
        event_sink=events.append,
        poll_interval_s=0.05,
    )
    br.seen_attempts = seen_attempts  # type: ignore[attr-defined]
    return br, ws, events


def test_free_task_choice_and_flip(tmp_path):
    br, ws, events = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"task_ids": ["t1", "t3"]})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)

    assert res["status"] == "ok"
    assert res["scope"] == "custom:2"
    assert res["n_tasks"] == 2  # only the two tasks we picked
    by_id = {t["task_id"]: t for t in res["per_task"]}
    assert set(by_id) == {"t1", "t3"}
    assert by_id["t1"]["flip"] == "fail->pass"
    assert by_id["t3"]["flip"] == ""
    assert res["n_fail_to_pass"] == 1
    assert res["budget"]["task_runs_used"] == 2
    assert res["budget"]["calls_used"] == 1


def test_unknown_task_ids_reported(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"task_ids": ["t1", "nope"]})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "ok"
    assert res["n_tasks"] == 1
    assert res["unknown_task_ids"] == ["nope"]


def test_smoke_shortcut_runs_all(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"subset": "smoke"})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "ok"
    assert res["scope"] == "smoke"
    assert res["n_tasks"] == 3  # smoke_size=3 covers all CPU train tasks


def test_budget_insufficient_then_exhausted(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=2, max_wall_clock_s=600)
    )
    br.start()
    try:
        # 1 task-run; ok, 1 remaining
        _submit(ws, EVAL_REQUEST_DIR, "a", {"task_ids": ["t1"]})
        assert _await_result(ws, EVAL_RESULT_DIR, "a")["status"] == "ok"
        # request of 3 > 1 remaining → insufficient (does not consume budget)
        _submit(ws, EVAL_REQUEST_DIR, "b", {"task_ids": ["t1", "t2", "t3"]})
        rb = _await_result(ws, EVAL_RESULT_DIR, "b")
        assert rb["status"] == "budget_insufficient"
        # 1 task-run; ok, now 0 remaining
        _submit(ws, EVAL_REQUEST_DIR, "c", {"task_ids": ["t2"]})
        assert _await_result(ws, EVAL_RESULT_DIR, "c")["status"] == "ok"
        # nothing left → exhausted
        _submit(ws, EVAL_REQUEST_DIR, "d", {"task_ids": ["t1"]})
        rd = _await_result(ws, EVAL_RESULT_DIR, "d")
        assert rd["status"] == "budget_exhausted"
        assert rd["budget"]["exhausted"] is True
    finally:
        br.stop(timeout=5)


def test_invalid_source_errors(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"task_ids": ["t1"], "source_rel": "nope"})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "error"
    assert "terminus-2 root" in res["error"]


def test_checkpoint_freezes_source(tmp_path):
    br, ws, events = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, CHECKPOINT_REQUEST_DIR, "ckpt_a", {"note": "from-scratch loop"})
        res = _await_result(ws, CHECKPOINT_RESULT_DIR, "ckpt_a")
        assert res["status"] == "ok"
        frozen = Path(res["frozen_source_path"])
        assert (frozen / "terminus_2" / "terminus_2.py").is_file()
        assert len(br.checkpoints) == 1
        # editing the workspace source must not change the frozen copy
        (ws / "terminus2_agent" / "terminus_2" / "terminus_2.py").write_text(
            "class Terminus2:\n    CHANGED = True\n", encoding="utf-8"
        )
        assert "CHANGED" not in (frozen / "terminus_2" / "terminus_2.py").read_text()
        assert any(e["event"] == "designer_checkpoint" for e in events)
    finally:
        br.stop(timeout=5)


def test_eval_surfaces_traces(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"task_ids": ["t1", "t2"]})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "ok"
    tdir = res["traces_dir"]
    assert tdir == f"{EVAL_RESULT_DIR}/r1__traces"
    t1log = ws / tdir / "t1.log"
    assert t1log.is_file() and "trajectory for t1" in t1log.read_text()
    assert (ws / tdir / "t2.log").is_file()


def test_n_attempts_passthrough(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    br.start()
    try:
        _submit(ws, EVAL_REQUEST_DIR, "r1", {"task_ids": ["t1"], "n_attempts": 3})
        res = _await_result(ws, EVAL_RESULT_DIR, "r1")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "ok"
    assert res["n_attempts"] == 3
    assert br.seen_attempts == [3]  # the runner_factory received n_attempts=3


def test_checkpoint_records_direction_and_diff_class(tmp_path):
    br, ws, _ = _make_bridge(
        tmp_path, DesignerBudget(max_eval_calls=10, max_task_runs=20, max_wall_clock_s=600)
    )
    # make the workspace source differ from baseline by a CODE change
    (ws / "terminus2_agent" / "terminus_2" / "terminus_2.py").write_text(
        "class Terminus2:\n    def run(self):\n        for i in range(3):\n"
        "            self.x = i\n        return 1\n",
        encoding="utf-8",
    )
    br.start()
    try:
        _submit(
            ws,
            CHECKPOINT_REQUEST_DIR,
            "ckpt_x",
            {"note": "loop", "direction": "ratchet", "mechanism": "best-snapshot"},
        )
        res = _await_result(ws, CHECKPOINT_RESULT_DIR, "ckpt_x")
    finally:
        br.stop(timeout=5)
    assert res["status"] == "ok"
    assert res["direction"] == "ratchet"
    assert res["diff_class"] == "code-level"
    rec = br.checkpoints[0]
    assert rec.direction_tag == "ratchet" and rec.mechanism == "best-snapshot"
    # archive.json persisted with the record
    archive = json.loads((tmp_path / "designer" / "archive.json").read_text())
    assert archive["checkpoints"][0]["direction_tag"] == "ratchet"
    assert archive["checkpoints"][0]["diff_class"] == "code-level"


def test_distinct_direction_floor_counts_only_code_level():
    from worldcalib.autolab.autolab_optimizer import AutolabOptimizer
    from worldcalib.autolab.eval_bridge import CheckpointRecord as CR

    cks = [
        CR("a", "/p/a", "", "", direction_tag="ratchet", diff_class="code-level"),
        CR("b", "/p/b", "", "", direction_tag="two-phase", diff_class="code-level"),
        CR("c", "/p/c", "", "", direction_tag="reflexion", diff_class="code-level"),
        CR("d", "/p/d", "", "", direction_tag="reword", diff_class="prompt-level"),
        # duplicate direction tag — should not double-count
        CR("e", "/p/e", "", "", direction_tag="ratchet", diff_class="code-level"),
    ]
    dirs = AutolabOptimizer._designer_distinct_directions(None, cks)
    assert dirs["n_distinct_code"] == 3  # ratchet, two-phase, reflexion
    assert dirs["n_prompt_level"] == 1
    assert set(dirs["code_directions"]) == {"ratchet", "two-phase", "reflexion"}


def test_check_and_done_clients(tmp_path):
    import subprocess
    import sys

    ws = tmp_path / "ws"
    (ws / EVAL_REQUEST_DIR).mkdir(parents=True)  # workspace-root marker
    tools = ws / ".worldcalib_tools"
    tools.mkdir()
    src = Path("src/worldcalib/autolab/_designer_tools")
    for n in ("check.py", "done.py"):
        (tools / n).write_text((src / n).read_text(), encoding="utf-8")
    pkg = ws / "terminus2_agent" / "terminus_2"
    pkg.mkdir(parents=True)

    # broken package -> check.py fails
    (pkg / "terminus_2.py").write_text("class Terminus2:\n    def run(self) ->\n", encoding="utf-8")
    r = subprocess.run([sys.executable, ".worldcalib_tools/check.py"], cwd=ws,
                       capture_output=True, text=True)
    assert r.returncode != 0 and "FAIL" in r.stdout

    # valid package -> check.py passes
    (pkg / "terminus_2.py").write_text(
        "class Terminus2:\n    def run(self):\n        return 1\n", encoding="utf-8"
    )
    r = subprocess.run([sys.executable, ".worldcalib_tools/check.py"], cwd=ws,
                       capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, (r.stdout, r.stderr)

    # done.py writes CONVERGED.md at the workspace root
    r = subprocess.run([sys.executable, ".worldcalib_tools/done.py", "--reason", "tried 3 dirs"],
                       cwd=ws, capture_output=True, text=True)
    assert r.returncode == 0
    assert (ws / "CONVERGED.md").is_file()
    assert "tried 3 dirs" in (ws / "CONVERGED.md").read_text()
