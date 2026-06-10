from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from worldcalib.coding.swebench import (
    DEFAULT_MINI_SWE_AGENT_NAME,
    MiniSweAgentSourceRunner,
    SwebenchInstance,
    _format_command,
    _rewrite_eval_entry_to_abs,
    load_swebench_instances,
    run_swebench_frontier,
)
from worldcalib.coding.swebench_optimizer import (
    EVAL_SCRIPT_BANNER,
    SwebenchOptimizer,
    SwebenchOptimizerConfig,
    _mirror_eval_script_into_candidate,
    detect_eval_script_tampering,
)


def test_load_swebench_instances_from_jsonl_selects_split_and_limit(tmp_path) -> None:
    data_path = tmp_path / "instances.jsonl"
    rows = [
        {"instance_id": "a", "problem_statement": "fix a", "split": "train"},
        {"instance_id": "b", "problem_statement": "fix b", "split": "test"},
        {"instance_id": "c", "problem_statement": "fix c", "split": "train"},
    ]
    data_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    instances = load_swebench_instances(data_path, split="train", limit=1)

    assert [item.task_id for item in instances] == ["a"]


def test_run_swebench_frontier_dry_run_writes_candidate_result(tmp_path) -> None:
    data_path = tmp_path / "instances.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "repo__issue-1",
                    "problem_statement": "Fix the regression.",
                    "repo": "owner/repo",
                    "split": "train",
                }
            ]
        ),
        encoding="utf-8",
    )

    summary = run_swebench_frontier(
        out_dir=tmp_path / "run",
        data_path=data_path,
        dry_run=True,
    )

    assert summary["benchmark"] == "swebench"
    assert summary["target_system"] == DEFAULT_MINI_SWE_AGENT_NAME
    assert summary["count"] == 1
    result_path = summary["candidates"][0]["result_path"]
    payload = json.loads(open(result_path, encoding="utf-8").read())
    assert payload["candidate"]["passrate"] == 0.0
    assert payload["tasks"][0]["metadata"]["dry_run"] is True
    assert payload["tasks"][0]["metadata"]["patch_path"].startswith(str(tmp_path))


def test_swebench_command_placeholders_are_absolute(tmp_path) -> None:
    source = tmp_path / "mini-swe-agent"
    task_dir = tmp_path / "run" / "agent_runs" / "candidate" / "repo__issue-1"
    instance_path = task_dir / "instance.json"
    patch_path = task_dir / "patch.diff"
    instance = SwebenchInstance(task_id="repo__issue-1", problem_statement="Fix it.")

    command = _format_command(
        "python runner.py --source-path {source_path} --instance-path {instance_path} "
        "--patch-path {patch_path} --task-dir {task_dir}",
        source_path=source,
        task_dir=task_dir,
        instance_path=instance_path,
        patch_path=patch_path,
        instance=instance,
    )

    assert command == [
        "python",
        "runner.py",
        "--source-path",
        str(source.resolve()),
        "--instance-path",
        str(instance_path.resolve()),
        "--patch-path",
        str(patch_path.resolve()),
        "--task-dir",
        str(task_dir.resolve()),
    ]


def test_swebench_instance_serializes_instance_id_alias() -> None:
    instance = SwebenchInstance(task_id="repo__issue-1", problem_statement="Fix it.")

    payload = instance.to_dict()

    assert payload["task_id"] == "repo__issue-1"
    assert payload["instance_id"] == "repo__issue-1"


def test_swebench_optimizer_copies_mini_source_snapshot(tmp_path) -> None:
    source = tmp_path / "mini-swe-agent"
    package = source / "mini_swe_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    data_path = tmp_path / "instances.json"
    data_path.write_text(
        json.dumps([{"instance_id": "x", "problem_statement": "fix x"}]),
        encoding="utf-8",
    )
    optimizer = SwebenchOptimizer(
        SwebenchOptimizerConfig(
            run_id="r",
            out_dir=tmp_path / "run",
            data_path=data_path,
            mini_swe_agent_source_path=source,
            dry_run=True,
        )
    )
    call_dir = tmp_path / "call"
    call_dir.mkdir()

    snapshot = optimizer._build_source_snapshot_workspace(
        iteration=1,
        source_family=DEFAULT_MINI_SWE_AGENT_NAME,
        call_dir=call_dir,
        target_system=DEFAULT_MINI_SWE_AGENT_NAME,
    )

    copied = snapshot / "candidate" / "upstream_source" / "mini-swe-agent"
    assert (copied / "mini_swe_agent" / "__init__.py").exists()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark"] == "swebench"
    assert manifest["mini_swe_agent_source"] == str(copied)


def test_rewrite_eval_entry_replaces_relative_script_with_absolute(tmp_path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        "# stub\n", encoding="utf-8"
    )

    tokens = [
        "python",
        "scripts/run_miniswe_swebench_single.py",
        "eval",
        "--source-path",
        "/some/source",
        "--patch-path",
        "/some/patch",
    ]

    rewritten = _rewrite_eval_entry_to_abs(tokens, project_root)

    assert rewritten[1] == str(project_root / "scripts" / "run_miniswe_swebench_single.py")
    # Everything else is unchanged so flag semantics survive.
    assert rewritten[0] == "python"
    assert rewritten[2:] == tokens[2:]


def test_rewrite_eval_entry_rewrites_absolute_path_to_trusted_root(tmp_path) -> None:
    project_root = tmp_path / "repo"
    abs_target = "/absolute/elsewhere/scripts/run_miniswe_swebench_single.py"
    tokens = ["python", abs_target, "eval"]

    rewritten = _rewrite_eval_entry_to_abs(tokens, project_root)

    assert rewritten == [
        "python",
        str(project_root / "scripts" / "run_miniswe_swebench_single.py"),
        "eval",
    ]


def test_rewrite_eval_entry_empty_command_is_noop(tmp_path) -> None:
    assert _rewrite_eval_entry_to_abs([], tmp_path) == []


def test_rewrite_eval_entry_applies_to_run_command_form(tmp_path) -> None:
    """run-command also goes through abs-path rewrite (symmetry with eval).

    Same defensive purpose: scripts/run_miniswe_swebench_single.py is the
    platform entry script for both `run` and `eval` subcommands. Letting
    baseline runs find the trusted copy when cwd=vendored mini-swe-agent
    (which has no scripts/) requires rewriting any candidate-supplied
    relative reference to the absolute repo-root path.
    """

    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        "", encoding="utf-8"
    )

    run_tokens = [
        "python",
        "scripts/run_miniswe_swebench_single.py",
        "run",
        "--source-path",
        "/some/source",
        "--model",
        "openai/deepseek-v4-pro",
    ]

    rewritten = _rewrite_eval_entry_to_abs(run_tokens, project_root)

    assert rewritten[1] == str(project_root / "scripts" / "run_miniswe_swebench_single.py")
    assert rewritten[2] == "run"
    # All non-entry tokens preserved.
    assert rewritten[2:] == run_tokens[2:]


def test_mirror_eval_script_creates_scripts_dir_and_writes_banner(tmp_path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    trusted_source = "print('trusted')\n"
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        trusted_source, encoding="utf-8"
    )
    candidate_mini = tmp_path / "snapshot" / "mini-swe-agent"
    candidate_mini.mkdir(parents=True)
    # No scripts/ exists in candidate yet — mirror must create it.
    assert not (candidate_mini / "scripts").exists()

    _mirror_eval_script_into_candidate(
        candidate_mini_root=candidate_mini,
        project_root=project_root,
    )

    target = candidate_mini / "scripts" / "run_miniswe_swebench_single.py"
    text = target.read_text(encoding="utf-8")
    assert text.startswith(EVAL_SCRIPT_BANNER)
    assert text.endswith(trusted_source)
    # And tampering detector sees no diff against trusted (banner stripped).
    assert detect_eval_script_tampering(candidate_mini, project_root) is False


def test_detect_eval_script_tampering_flags_modified_copy(tmp_path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        "trusted body\n", encoding="utf-8"
    )
    candidate_mini = tmp_path / "snapshot" / "mini-swe-agent"
    candidate_mini.mkdir(parents=True)
    _mirror_eval_script_into_candidate(
        candidate_mini_root=candidate_mini,
        project_root=project_root,
    )

    # Proposer rewrites the in-candidate copy.
    target = candidate_mini / "scripts" / "run_miniswe_swebench_single.py"
    target.write_text("hacked body\n", encoding="utf-8")

    assert detect_eval_script_tampering(candidate_mini, project_root) is True


def test_detect_eval_script_tampering_flags_missing_copy(tmp_path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        "trusted\n", encoding="utf-8"
    )
    candidate_mini = tmp_path / "snapshot" / "mini-swe-agent"
    candidate_mini.mkdir(parents=True)
    # No mirror; no candidate copy. Treated as tampering.
    assert detect_eval_script_tampering(candidate_mini, project_root) is True


def test_candidate_policy_scan_skips_mirrored_eval_script(tmp_path) -> None:
    """The mirrored eval-gate copy contains 'swebench.harness' legitimately.

    Regression test for an A2 side-effect: the trusted eval script
    references swebench.harness.run_evaluation (it IS the scorer entry).
    When mirrored into a candidate snapshot for proposer reference, the
    code-policy scanner must NOT flag this copy as a violation, because
    eval-gate integrity is enforced separately via sha256 detection.
    """

    edited_source = tmp_path / "edited-mini"
    edited_source.mkdir()
    # Mirror a file under scripts/ that contains the marker, mimicking
    # _mirror_eval_script_into_candidate's output.
    (edited_source / "scripts").mkdir()
    (edited_source / "scripts" / "run_miniswe_swebench_single.py").write_text(
        "# READ-ONLY REFERENCE\nimport subprocess\nsubprocess.run(['python', '-m', 'swebench.harness.run_evaluation'])\n",
        encoding="utf-8",
    )
    # Also place a benign agent file so the scan path is non-trivial.
    (edited_source / "src").mkdir()
    (edited_source / "src" / "agent.py").write_text(
        "def respond(): return 'hello'\n", encoding="utf-8"
    )

    optimizer = SwebenchOptimizer(
        SwebenchOptimizerConfig(
            run_id="r",
            out_dir=tmp_path / "run",
            data_path=tmp_path / "instances.json",
            mini_swe_agent_source_path=tmp_path / "default-mini",
            dry_run=True,
        )
    )
    candidate = {
        "name": "c",
        "extra": {"source_project_path": str(edited_source)},
    }
    optimizer._normalize_candidate_source_project_path(candidate)

    violations = optimizer._candidate_code_policy_violations(candidate)

    # The benign agent.py contains no markers; the mirrored eval script
    # is skipped. So no swebench.harness violation should appear for the
    # mirrored eval-gate path.
    assert not any(
        v.get("marker") == "swebench.harness"
        and v.get("path", "").endswith("run_miniswe_swebench_single.py")
        for v in violations
    ), f"unexpected violation flagged for mirrored eval gate: {violations}"


def test_mirror_eval_script_overwrites_tampered_copy(tmp_path) -> None:
    """Re-mirroring after tampering resets the in-snapshot copy.

    Models the A3 strengthening: when sha256 detection flags tampering, the
    optimizer calls _mirror_eval_script_into_candidate again to reset the
    copy so a later curaii-style iteration's copytree() inherits the
    trusted version, not the hacked one.
    """

    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    trusted_text = "def eval_patch(): pass\n"
    (project_root / "scripts" / "run_miniswe_swebench_single.py").write_text(
        trusted_text, encoding="utf-8"
    )
    candidate_mini = tmp_path / "snapshot" / "mini-swe-agent"
    candidate_mini.mkdir(parents=True)
    _mirror_eval_script_into_candidate(
        candidate_mini_root=candidate_mini,
        project_root=project_root,
    )
    target = candidate_mini / "scripts" / "run_miniswe_swebench_single.py"

    # Proposer hacks the copy.
    target.write_text("def eval_patch(): return 0  # always pass\n", encoding="utf-8")
    assert detect_eval_script_tampering(candidate_mini, project_root) is True

    # Optimizer re-mirrors after detection.
    _mirror_eval_script_into_candidate(
        candidate_mini_root=candidate_mini,
        project_root=project_root,
    )

    # Trusted body restored; banner re-applied; detector clears.
    text = target.read_text(encoding="utf-8")
    assert text.startswith(EVAL_SCRIPT_BANNER)
    assert text.endswith(trusted_text)
    assert detect_eval_script_tampering(candidate_mini, project_root) is False


def test_swebench_candidate_uses_extra_source_project_path(tmp_path) -> None:
    default_source = tmp_path / "default-mini"
    edited_source = tmp_path / "edited-mini"
    default_source.mkdir()
    edited_source.mkdir()
    optimizer = SwebenchOptimizer(
        SwebenchOptimizerConfig(
            run_id="r",
            out_dir=tmp_path / "run",
            data_path=tmp_path / "instances.json",
            mini_swe_agent_source_path=default_source,
            dry_run=True,
        )
    )
    candidate = {
        "name": "edited",
        "extra": {
            "source_project_path": str(edited_source),
        },
    }

    optimizer._normalize_candidate_source_project_path(candidate)

    assert candidate["source_project_path"] == str(edited_source)


def _load_miniswe_runner_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_miniswe_swebench_single.py"
    spec = importlib.util.spec_from_file_location("run_miniswe_swebench_single", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_miniswe_runner_recovers_patch_from_trajectory_when_preds_missing(tmp_path) -> None:
    module = _load_miniswe_runner_module()
    output = tmp_path / "miniswe_run"
    traj_dir = output / "repo__issue-1"
    traj_dir.mkdir(parents=True)
    patch = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n"
    (traj_dir / "repo__issue-1.traj.json").write_text(
        json.dumps({"info": {"exit_status": "AutoSubmittedDueToTime", "submission": patch}}),
        encoding="utf-8",
    )

    assert module._read_patch_from_trajectory(output, "repo__issue-1") == patch


def test_miniswe_runner_keeps_api_key_out_of_argv(tmp_path, monkeypatch) -> None:
    module = _load_miniswe_runner_module()
    source = tmp_path / "mini-swe-agent"
    source.mkdir()
    task_dir = tmp_path / "task"
    instance_path = task_dir / "instance.json"
    patch_path = task_dir / "patch.diff"
    task_dir.mkdir()
    instance_path.write_text(json.dumps({"instance_id": "repo__issue-1"}), encoding="utf-8")
    captured = {}

    def fake_run(cmd, *, cwd, env, text, capture_output, check):
        captured["cmd"] = list(cmd)
        captured["env"] = dict(env)
        output = task_dir / "miniswe_run"
        output.mkdir(parents=True, exist_ok=True)
        (output / "preds.json").write_text(
            json.dumps({"repo__issue-1": {"model_patch": "diff --git a/x b/x\n"}}),
            encoding="utf-8",
        )
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("TOGETHER_API_KEY", "secret-token")
    args = SimpleNamespace(
        source_path=source,
        task_dir=task_dir,
        patch_path=patch_path,
        instance_path=instance_path,
        model="openai/model",
        base_url="https://example.test/v1",
        api_key=None,
        api_key_env="TOGETHER_API_KEY",
        step_limit=0,
        max_tokens=128,
    )

    assert module.run_agent(args, root=tmp_path, instance_id="repo__issue-1") == 0
    assert "secret-token" not in " ".join(captured["cmd"])
    assert captured["env"]["OPENAI_API_KEY"] == "secret-token"
    assert patch_path.read_text(encoding="utf-8") == "diff --git a/x b/x\n"


def test_swebench_runner_records_timeout_without_late_patch(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    data = [SwebenchInstance(task_id="repo__issue-1", problem_statement="fix it")]
    runner = MiniSweAgentSourceRunner(
        instances=data,
        out_dir=tmp_path / "run",
        timeout_s=1,
        project_root=Path.cwd(),
    )

    result = runner.evaluate_candidate(
        candidate={
            "source_project_path": str(source),
            "command": "python -c 'import time; time.sleep(5)'",
            "eval_command": "python -c 'raise SystemExit(0)'",
        },
        candidate_id="slow",
    )

    payload = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
    task = payload["tasks"][0]
    assert task["metadata"]["timed_out"] is True
    assert task["prediction"] == ""
    assert Path(task["metadata"]["patch_path"]).read_text(encoding="utf-8") == ""


def test_swebench_source_snapshot_diff_includes_upstream_edits(tmp_path) -> None:
    source = tmp_path / "mini-swe-agent"
    agent_file = source / "src" / "minisweagent" / "agents" / "default.py"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text("VALUE = 'old'\n", encoding="utf-8")
    data_path = tmp_path / "instances.json"
    data_path.write_text(
        json.dumps([{"instance_id": "x", "problem_statement": "fix x"}]),
        encoding="utf-8",
    )
    optimizer = SwebenchOptimizer(
        SwebenchOptimizerConfig(
            run_id="r",
            out_dir=tmp_path / "run",
            data_path=data_path,
            mini_swe_agent_source_path=source,
            dry_run=True,
        )
    )
    call_dir = tmp_path / "call"
    snapshot = optimizer._build_source_snapshot_workspace(
        iteration=1,
        source_family=DEFAULT_MINI_SWE_AGENT_NAME,
        call_dir=call_dir,
        target_system=DEFAULT_MINI_SWE_AGENT_NAME,
        snapshot_root=call_dir / "source_snapshot",
    )
    edited = (
        snapshot
        / "candidate"
        / "upstream_source"
        / "mini-swe-agent"
        / "src"
        / "minisweagent"
        / "agents"
        / "default.py"
    )
    edited.write_text("VALUE = 'new'\n", encoding="utf-8")

    optimizer._write_source_snapshot_diff(call_dir)

    diff = (call_dir / "diff.patch").read_text(encoding="utf-8")
    assert "default.py" in diff
    assert "-VALUE = 'old'" in diff
    assert "+VALUE = 'new'" in diff
