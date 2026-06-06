"""AutoLab benchmark support — terminus-2 harness-config candidates via harbor.

AutoLab (https://github.com/autolabhq/autolab) is a 36-task agent-eval suite in
the Terminal-Bench / Harbor family. Each task ships a docker environment, an
agent-facing ``instruction.md``, a reference ``solution/`` (never read at eval),
and a ``tests/`` verifier that emits a *continuous* reward in ``[0, 1]`` (0.5 is
anchored to a human reference solution).

WorldCalib's own venv has no harbor; the canonical harbor binary lives in a
separate venv (``/data/home/yuhan/cyh_dev/bin/harbor``). This module therefore
shells out to that binary via subprocess — directly mirroring how
``MiniSweAgentSourceRunner`` shells out to the mini-SWE-agent eval gate. It then
walks harbor's per-trial output tree, reads each trial's ``verifier/reward.*``
(preferring the bare-float ``reward.txt``), aggregates per-task Avg@k and
Best@k, and builds a :class:`CandidateResult` whose ``TaskResult.score`` is the
*continuous* reward (``passed = reward >= gate``).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.schemas import CandidateResult, TaskResult


# ---------------------------------------------------------------------------
# Defaults (verified ground truth from the task spec).
# ---------------------------------------------------------------------------
DEFAULT_AUTOLAB_TASKS_PATH = Path("third_party/autolab/tasks")
DEFAULT_AUTOLAB_AGENT = "terminus-2"
DEFAULT_AUTOLAB_SCAFFOLD_NAME = "terminus2_autolab"
DEFAULT_AUTOLAB_MODEL = "deepseek-v4-pro[1m]"
DEFAULT_HARBOR_PYTHON = Path("/data/home/yuhan/cyh_dev/bin/python")
DEFAULT_HARBOR_BINARY = Path("/data/home/yuhan/cyh_dev/bin/harbor")
DEFAULT_REWARD_GATE = 0.5

# Editable-harness (Option B) surface. The proposer optimizes an editable COPY of
# harbor's terminus-2 agent package (prompt templates + control flow). The copy
# is a Python package ``terminus_2/`` living under a parent dir we put on
# PYTHONPATH; harbor loads it via ``--agent-import-path`` instead of ``-a``.
# DEFAULT_TERMINUS2_SOURCE is the vendored pristine copy (the seed/baseline);
# proposed candidates carry an edited snapshot via ``agent_source_path``.
DEFAULT_TERMINUS2_SOURCE = Path("references/vendor/terminus2_agent")
TERMINUS2_IMPORT_PATH = "terminus_2.terminus_2:Terminus2"
# Relative marker that makes a dir a valid terminus-2 source root (the parent of
# the importable ``terminus_2`` package).
_TERMINUS2_PKG_MARKER = Path("terminus_2") / "terminus_2.py"

# How harbor's terminus-2 must be patched in the cyh_dev site-packages for all
# 36 tasks to run. We grep the installed source for these post-patch markers and
# fail fast (with a clear message) when they are absent. We do NOT mutate the
# foreign venv ourselves — that is a one-time operator step (see module docs /
# task spec §0.1).
_HARBOR_PKG_DIR = Path("/data/home/yuhan/cyh_dev/lib/python3.12/site-packages/harbor")
_PATCH_DURATION_FILE = _HARBOR_PKG_DIR / "agents" / "terminus_2" / "terminus_2.py"
_PATCH_DURATION_MARKER = "min(parsed_cmd.duration, 1200)"
_PATCH_GPU_FILE = _HARBOR_PKG_DIR / "environments" / "docker" / "docker.py"
# The GPU patch flips ``supports_gpus`` from ``return False`` to ``return True``.
# Detect the UNPATCHED signature directly — a bare ``"return True"`` substring is
# useless here because docker.py returns True in many other methods.
_PATCH_GPU_UNPATCHED = "def supports_gpus(self) -> bool:\n        return False"


@dataclass(frozen=True)
class AutolabTask:
    """One AutoLab task parsed from ``task.toml`` + ``instruction.md``.

    Mirrors :class:`SwebenchInstance`: a frozen row the runner can map a harbor
    trial back onto via ``task_id`` (== the task directory name == harbor's
    ``task_name``, since AutoLab ``task.toml`` declares no ``[task].name``).
    """

    task_id: str
    instruction: str
    path: Path
    domain: str = ""
    difficulty: str = ""
    library: str = ""
    agent_timeout_sec: int = 0
    verifier_timeout_sec: int = 0
    cpus: int = 0
    memory_mb: int = 0
    storage_mb: int = 0
    gpus: int = 0
    gpu_types: tuple[str, ...] = ()
    allow_internet: bool = False
    build_timeout_sec: int = 0
    metric: str = ""
    direction: str = ""
    baseline_score: float = 0.0
    reference_score: float = 0.0
    split: str = "train"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_task_dir(cls, task_dir: Path) -> "AutolabTask":
        task_dir = Path(task_dir)
        toml_path = task_dir / "task.toml"
        if not toml_path.is_file():
            raise FileNotFoundError(f"AutoLab task is missing task.toml: {toml_path}")
        instruction_path = task_dir / "instruction.md"
        if not instruction_path.is_file():
            raise FileNotFoundError(
                f"AutoLab task is missing instruction.md: {instruction_path}"
            )
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        instruction = instruction_path.read_text(encoding="utf-8")
        return cls.from_task_toml(
            data,
            task_id=task_dir.name,
            instruction=instruction,
            path=task_dir,
        )

    @classmethod
    def from_task_toml(
        cls,
        data: Mapping[str, Any],
        *,
        task_id: str,
        instruction: str,
        path: Path,
    ) -> "AutolabTask":
        meta = data.get("metadata", {}) if isinstance(data.get("metadata"), Mapping) else {}
        agent = data.get("agent", {}) if isinstance(data.get("agent"), Mapping) else {}
        verifier = data.get("verifier", {}) if isinstance(data.get("verifier"), Mapping) else {}
        env = data.get("environment", {}) if isinstance(data.get("environment"), Mapping) else {}
        opt = data.get("optimization", {}) if isinstance(data.get("optimization"), Mapping) else {}
        baseline = opt.get("baseline", {}) if isinstance(opt.get("baseline"), Mapping) else {}
        reference = opt.get("reference", {}) if isinstance(opt.get("reference"), Mapping) else {}

        # GPU-types normalization: accept plural ``gpu_types`` or the singular
        # ``gpu_type`` typo (flux2_klein_lora); CPU-only tasks → ().
        gpu_types_raw = env.get("gpu_types")
        if gpu_types_raw:
            gpu_types = tuple(str(x) for x in gpu_types_raw)
        elif env.get("gpu_type"):
            gpu_types = (str(env["gpu_type"]),)
        else:
            gpu_types = ()

        verifier_env = (
            dict(verifier.get("env", {}))
            if isinstance(verifier.get("env"), Mapping)
            else {}
        )
        metadata: dict[str, Any] = {
            "tags": meta.get("tags"),
            "author": meta.get("author"),
            "version": meta.get("version"),
            "verifier_env": verifier_env,
            "baseline_method": baseline.get("method"),
            "reference_method": reference.get("method"),
            "tier": opt.get("tier"),
            "constraints": opt.get("constraints"),
            "search_space": opt.get("search_space"),
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return cls(
            task_id=task_id,
            instruction=instruction,
            path=Path(path),
            domain=str(meta.get("domain", "")),
            difficulty=str(meta.get("difficulty", "")),
            library=str(meta.get("library", "")),
            agent_timeout_sec=int(agent.get("timeout_sec", 0) or 0),
            verifier_timeout_sec=int(verifier.get("timeout_sec", 0) or 0),
            cpus=int(env.get("cpus", 0) or 0),
            memory_mb=int(env.get("memory_mb", 0) or 0),
            storage_mb=int(env.get("storage_mb", 0) or 0),
            gpus=int(env.get("gpus", 0) or 0),
            gpu_types=gpu_types,
            allow_internet=bool(env.get("allow_internet", False)),
            build_timeout_sec=int(env.get("build_timeout_sec", 0) or 0),
            metric=str(opt.get("metric", "")),
            direction=str(opt.get("direction", "")),
            baseline_score=float(baseline.get("score", 0.0) or 0.0),
            reference_score=float(reference.get("score", 0.0) or 0.0),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True)
class AutolabAttempt:
    """One harbor trial (one of the ``-k`` attempts) on one AutoLab task."""

    reward: float
    passed: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errored: bool = False
    trial_name: str = ""
    trial_dir: str = ""


def load_autolab_tasks(
    tasks_root: Path | None,
    *,
    split: str = "train",
    limit: int = 0,
    task_ids: tuple[str, ...] | list[str] | None = None,
    categories: tuple[str, ...] | list[str] | None = None,
) -> list[AutolabTask]:
    """Load AutoLab tasks. Default (no filters) returns all 36, sorted by id.

    ``split`` is accepted for parity with the swebench loader; AutoLab has no
    frozen split file, so every task is assigned ``split="train"`` and a
    requested split with no matches falls back to returning everything
    (mirrors :func:`load_swebench_instances`).
    """

    root = Path(tasks_root) if tasks_root is not None else DEFAULT_AUTOLAB_TASKS_PATH
    if not root.is_dir():
        raise FileNotFoundError(f"AutoLab tasks dir does not exist: {root}")
    dirs = sorted(
        p for p in root.iterdir() if p.is_dir() and (p / "task.toml").is_file()
    )
    tasks = [AutolabTask.from_task_dir(d) for d in dirs]

    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in tasks if t.task_id in wanted]
    if categories:
        cats = set(categories)
        tasks = [t for t in tasks if t.domain in cats]

    selected = [t for t in tasks if t.split == split]
    if not selected:
        selected = tasks
    if limit:
        selected = selected[:limit]
    return selected


def verify_harbor_patched(harbor_pkg_dir: Path = _HARBOR_PKG_DIR) -> list[str]:
    """Return a list of missing-patch messages (empty == fully patched).

    Greps the installed cyh_dev harbor source for the two load-bearing patches
    (terminus-2 1200s command ceiling, docker GPU passthrough). GPU tasks and
    long benchmarks need these; we never mutate the foreign venv ourselves.
    """

    problems: list[str] = []
    duration_file = harbor_pkg_dir / "agents" / "terminus_2" / "terminus_2.py"
    gpu_file = harbor_pkg_dir / "environments" / "docker" / "docker.py"
    try:
        if _PATCH_DURATION_MARKER not in duration_file.read_text(encoding="utf-8"):
            problems.append(
                f"terminus-2 command-duration patch missing in {duration_file} "
                f"(expected marker {_PATCH_DURATION_MARKER!r}); long builds will "
                "be truncated at 60s. Apply harbor_patch.sh against cyh_dev."
            )
    except OSError as exc:
        problems.append(f"cannot read {duration_file}: {exc}")
    try:
        gpu_text = gpu_file.read_text(encoding="utf-8")
        if "supports_gpus" not in gpu_text or _PATCH_GPU_UNPATCHED in gpu_text:
            problems.append(
                f"docker GPU-passthrough patch missing in {gpu_file}; the 12 "
                "gpus=1 tasks cannot run. Apply harbor_patch.sh against cyh_dev."
            )
    except OSError as exc:
        problems.append(f"cannot read {gpu_file}: {exc}")
    return problems


class AutolabHarborRunner:
    """Evaluate a terminus-2 harness-config candidate on AutoLab via harbor.

    The candidate is a *config dict* (agent kwargs / model / env), never an
    editable source tree — so this runner never imports candidate code. It
    builds an argv for the cyh_dev ``harbor run`` binary, subsets the 36-task
    dataset dir with ``-i <task_id>`` filters, runs it under a process-group
    kill-on-timeout wrapper, then walks the per-trial output tree and reads each
    ``verifier/reward.*`` to aggregate Avg@k / Best@k per task.
    """

    def __init__(
        self,
        *,
        tasks: list[AutolabTask],
        out_dir: Path,
        harbor_binary: Path = DEFAULT_HARBOR_BINARY,
        harbor_python: Path = DEFAULT_HARBOR_PYTHON,
        harbor_agent: str = DEFAULT_AUTOLAB_AGENT,
        harbor_model: str = DEFAULT_AUTOLAB_MODEL,
        n_attempts: int = 1,
        timeout_multiplier: float = 1.0,
        concurrency: int = 4,
        env_file: Path | None = None,
        reward_gate: float = DEFAULT_REWARD_GATE,
        score_mode: str = "best",
        eval_timeout_s: int = 300,
        max_eval_workers: int = 1,
        dry_run: bool = False,
        force: bool = False,
        verify_patches: bool = True,
        gpu_devices: str | None = None,
    ) -> None:
        self.tasks = tasks
        self.out_dir = out_dir
        self.harbor_binary = Path(harbor_binary)
        self.harbor_python = Path(harbor_python)
        self.harbor_agent = harbor_agent
        self.harbor_model = harbor_model
        self.n_attempts = max(1, int(n_attempts))
        self.timeout_multiplier = float(timeout_multiplier)
        self.concurrency = max(1, int(concurrency))
        self.env_file = Path(env_file) if env_file is not None else None
        self.reward_gate = float(reward_gate)
        self.score_mode = score_mode if score_mode in ("best", "avg") else "best"
        self.eval_timeout_s = int(eval_timeout_s)
        self.max_eval_workers = max(1, int(max_eval_workers))
        self.dry_run = dry_run
        self.force = force
        self.verify_patches = verify_patches
        self.gpu_devices = gpu_devices

    # -- public API ---------------------------------------------------------

    def evaluate_candidate(
        self,
        *,
        candidate: Mapping[str, Any],
        candidate_id: str,
        agent_name: str = DEFAULT_AUTOLAB_SCAFFOLD_NAME,
    ) -> CandidateResult:
        candidate_dir = self.out_dir / "candidate_results"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        result_path = candidate_dir / f"{candidate_id}.json"
        if not self.force:
            existing = _load_candidate_result(
                result_path,
                candidate_id=candidate_id,
                agent_name=agent_name,
                config=dict(candidate),
            )
            if existing is not None:
                return existing

        if self.max_eval_workers == 1 or len(self.tasks) <= 1:
            task_results = [
                self._evaluate_task(candidate, candidate_id=candidate_id, task=task)
                for task in self.tasks
            ]
        else:
            workers = min(self.max_eval_workers, len(self.tasks))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                task_results = list(
                    pool.map(
                        lambda task: self._evaluate_task(
                            candidate, candidate_id=candidate_id, task=task
                        ),
                        self.tasks,
                    )
                )

        count = len(task_results)
        passrate = sum(1 for t in task_results if t.passed) / count if count else 0.0
        average_score = sum(t.score for t in task_results) / count if count else 0.0
        prompt_tokens = sum(t.prompt_tokens for t in task_results)
        completion_tokens = sum(t.completion_tokens for t in task_results)
        token_consuming = prompt_tokens + completion_tokens
        result = CandidateResult(
            candidate_id=candidate_id,
            scaffold_name=agent_name,
            passrate=passrate,
            average_score=average_score,
            token_consuming=token_consuming,
            avg_token_consuming=(token_consuming / count if count else 0.0),
            avg_prompt_tokens=(prompt_tokens / count if count else 0.0),
            avg_completion_tokens=(completion_tokens / count if count else 0.0),
            count=count,
            config=dict(candidate),
            result_path=str(result_path),
        )
        payload = {
            "candidate": result.to_dict(),
            "tasks": [t.to_dict() for t in task_results],
            "score_breakdown": _score_breakdown(task_results),
        }
        result_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result

    # -- per-task evaluation -----------------------------------------------

    def _evaluate_task(
        self,
        candidate: Mapping[str, Any],
        *,
        candidate_id: str,
        task: AutolabTask,
    ) -> TaskResult:
        if self.dry_run:
            return TaskResult(
                task_id=task.task_id,
                question=task.instruction,
                gold_answer="",
                prediction="",
                score=0.0,
                passed=False,
                prompt_tokens=0,
                completion_tokens=0,
                retrieved=[],
                metadata=self._base_metadata(task, dry_run=True),
            )

        if self.verify_patches:
            problems = verify_harbor_patched(_HARBOR_PKG_DIR)
            if problems:
                raise RuntimeError(
                    "cyh_dev harbor is not patched for AutoLab:\n  - "
                    + "\n  - ".join(problems)
                )

        jobs_dir = self.out_dir / "agent_runs" / candidate_id / task.task_id
        jobs_dir.mkdir(parents=True, exist_ok=True)
        job_name = f"{candidate_id}__{task.task_id}"[:96]

        agent_source = self._candidate_agent_source_dir(candidate)
        argv = self._build_argv(
            task=task,
            candidate=candidate,
            jobs_dir=jobs_dir,
            job_name=job_name,
            agent_source=agent_source,
        )
        (jobs_dir / "harbor_command.txt").write_text(
            " ".join(argv), encoding="utf-8"
        )

        per_task_timeout = self._task_timeout(task)
        started = time.time()
        returncode: int | None = None
        timed_out = False
        try:
            completed = _run_subprocess_with_timeout(
                argv,
                cwd=Path.cwd(),
                timeout=per_task_timeout,
                extra_env=self._subprocess_env(agent_source),
            )
            returncode = completed.returncode
            (jobs_dir / "harbor_stdout.txt").write_text(
                completed.stdout, encoding="utf-8"
            )
            (jobs_dir / "harbor_stderr.txt").write_text(
                completed.stderr, encoding="utf-8"
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            (jobs_dir / "harbor_stdout.txt").write_text(
                _timeout_output_to_text(exc.stdout), encoding="utf-8"
            )
            (jobs_dir / "harbor_stderr.txt").write_text(
                _timeout_output_to_text(exc.stderr), encoding="utf-8"
            )
        duration_s = time.time() - started

        attempts = _collect_attempts(
            job_dir=jobs_dir / job_name,
            task_id=task.task_id,
            gate=self.reward_gate,
        )
        return self._build_task_result(
            task=task,
            attempts=attempts,
            job_dir=jobs_dir / job_name,
            returncode=returncode,
            timed_out=timed_out,
            duration_s=duration_s,
        )

    def _build_task_result(
        self,
        *,
        task: AutolabTask,
        attempts: list[AutolabAttempt],
        job_dir: Path,
        returncode: int | None,
        timed_out: bool,
        duration_s: float,
    ) -> TaskResult:
        metadata = self._base_metadata(task)
        metadata.update(
            {
                "jobs_dir": str(job_dir),
                "returncode": returncode,
                "timed_out": timed_out,
                "duration_s": duration_s,
            }
        )
        if not attempts:
            metadata["missing"] = True
            metadata["k"] = 0
            return TaskResult(
                task_id=task.task_id,
                question=task.instruction,
                gold_answer="",
                prediction="",
                score=0.0,
                passed=False,
                prompt_tokens=0,
                completion_tokens=0,
                retrieved=[],
                metadata=metadata,
            )

        rewards = [a.reward for a in attempts]
        avg_at_k = sum(rewards) / len(rewards)
        best_at_k = max(rewards)
        best_attempt = max(attempts, key=lambda a: a.reward)
        if self.score_mode == "avg":
            score = avg_at_k
            passed = avg_at_k >= self.reward_gate
        else:
            score = best_at_k
            passed = any(a.passed for a in attempts)
        metadata.update(
            {
                "reward": best_attempt.reward,
                "avg_at_k": avg_at_k,
                "best_at_k": best_at_k,
                "k": len(attempts),
                "rewards": rewards,
                "n_errored": sum(1 for a in attempts if a.errored),
                "trial_dir": best_attempt.trial_dir,
                "raw_metric_value": None,
            }
        )
        return TaskResult(
            task_id=task.task_id,
            question=task.instruction,
            gold_answer="",
            prediction=best_attempt.trial_name,
            score=float(score),
            passed=bool(passed),
            prompt_tokens=sum(a.prompt_tokens for a in attempts),
            completion_tokens=sum(a.completion_tokens for a in attempts),
            retrieved=[],
            metadata=metadata,
        )

    def _base_metadata(self, task: AutolabTask, *, dry_run: bool = False) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "benchmark": "autolab",
            "agent": self.harbor_agent,
            "model": self.harbor_model,
            "domain": task.domain,
            "metric": task.metric,
            "direction": task.direction,
            "baseline_score": task.baseline_score,
            "reference_score": task.reference_score,
            "gpus": task.gpus,
        }
        if dry_run:
            meta["dry_run"] = True
        return meta

    # -- argv / env construction -------------------------------------------

    def _build_argv(
        self,
        *,
        task: AutolabTask,
        candidate: Mapping[str, Any],
        jobs_dir: Path,
        job_name: str,
        agent_source: Path | None = None,
    ) -> list[str]:
        model = str(candidate.get("model") or self.harbor_model)
        multiplier = float(candidate.get("timeout_multiplier") or self.timeout_multiplier)
        argv: list[str] = [
            str(self.harbor_binary),
            "run",
            "-p",
            str(task.path),
            "-i",
            task.task_id,
        ]
        # Option B: if the candidate carries an editable terminus-2 source tree,
        # load it via --agent-import-path (PYTHONPATH is set in _subprocess_env)
        # instead of the installed `-a terminus-2`. The seed/baseline (no source)
        # uses the installed agent.
        if agent_source is not None:
            argv += ["--agent-import-path", TERMINUS2_IMPORT_PATH]
        else:
            argv += ["-a", self.harbor_agent]
        argv += [
            "-m",
            model,
            "-o",
            str(jobs_dir),
            "--job-name",
            job_name,
            "-k",
            str(self.n_attempts),
            "-n",
            "1",
            "--timeout-multiplier",
            str(multiplier),
            "-y",
            "--quiet",
        ]
        if self.env_file is not None:
            argv += ["--env-file", str(self.env_file)]
        for key, value in _candidate_agent_kwargs(candidate).items():
            argv += ["--ak", f"{key}={_render_ak_value(value)}"]
        for key, value in _candidate_agent_env(candidate).items():
            argv += ["--ae", f"{key}={value}"]
        return argv

    def _subprocess_env(self, agent_source: Path | None = None) -> dict[str, str]:
        env = dict(os.environ)
        if self.gpu_devices is not None:
            env["HARBOR_GPU_DEVICES"] = str(self.gpu_devices)
        if agent_source is not None:
            # Make the editable `terminus_2` package importable by the cyh_dev
            # harbor process so --agent-import-path terminus_2.terminus_2 resolves
            # to the EDITED copy, not the installed one. Prepend so it wins.
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{agent_source}{os.pathsep}{prev}" if prev else str(agent_source)
            )
        return env

    def _candidate_agent_source_dir(self, candidate: Mapping[str, Any]) -> Path | None:
        """Resolve the editable terminus-2 source root from a candidate.

        Returns the directory that CONTAINS the importable ``terminus_2`` package
        (so it can go on PYTHONPATH), or ``None`` when the candidate carries no
        source (seed/baseline → installed ``-a terminus-2``). Raises when a source
        is named but is not a valid terminus-2 tree, so a broken candidate fails
        loudly rather than silently grading the unedited baseline.
        """

        extra = candidate.get("extra") if isinstance(candidate.get("extra"), Mapping) else {}
        raw = None
        for key in ("agent_source_path", "source_project_path", "terminus2_source_path"):
            raw = candidate.get(key) or extra.get(key)
            if raw:
                break
        if not raw:
            return None
        path = Path(str(raw)).expanduser()
        if not (path / _TERMINUS2_PKG_MARKER).is_file():
            raise FileNotFoundError(
                f"candidate agent_source_path {path} is not a valid terminus-2 source root "
                f"(missing {_TERMINUS2_PKG_MARKER}); expected the parent dir of the "
                "terminus_2 package."
            )
        return path

    def _task_timeout(self, task: AutolabTask) -> int:
        """Per-``harbor run`` subprocess wall-clock ceiling.

        Derive from the task's own ``[agent]``/``[verifier]`` timeouts scaled by
        the multiplier, plus build time and generous slack — harbor's internal
        per-trial timeouts should fire first. Never go below ``eval_timeout_s``.
        """

        base = task.agent_timeout_sec * self.timeout_multiplier
        base += task.verifier_timeout_sec * self.timeout_multiplier
        base += task.build_timeout_sec
        base += 900  # slack for image build / harbor overhead
        base *= max(1, self.n_attempts)
        return max(self.eval_timeout_s, int(base))


# ---------------------------------------------------------------------------
# Frontier (seed-baseline eval).
# ---------------------------------------------------------------------------
def run_autolab_frontier(
    *,
    out_dir: Path,
    tasks_path: Path | None = None,
    split: str = "train",
    limit: int = 0,
    task_ids: tuple[str, ...] = (),
    harbor_binary: Path = DEFAULT_HARBOR_BINARY,
    harbor_python: Path = DEFAULT_HARBOR_PYTHON,
    harbor_agent: str = DEFAULT_AUTOLAB_AGENT,
    harbor_model: str = DEFAULT_AUTOLAB_MODEL,
    n_attempts: int = 1,
    timeout_multiplier: float = 1.0,
    concurrency: int = 4,
    env_file: Path | None = None,
    reward_gate: float = DEFAULT_REWARD_GATE,
    eval_timeout_s: int = 300,
    max_eval_workers: int = 1,
    dry_run: bool = False,
    force: bool = False,
    verify_patches: bool = True,
    pareto_quality_threshold: float = 0.125,
) -> dict[str, Any]:
    """Evaluate the plain terminus-2 baseline (no agent-kwarg edits)."""

    tasks = load_autolab_tasks(
        tasks_path, split=split, limit=limit, task_ids=task_ids or None
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate: dict[str, Any] = {
        "name": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        "scaffold_name": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        "agent_name": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        "model": harbor_model,
        "agent_kwargs": {},
        "agent_env": {},
    }
    runner = AutolabHarborRunner(
        tasks=tasks,
        out_dir=out_dir,
        harbor_binary=harbor_binary,
        harbor_python=harbor_python,
        harbor_agent=harbor_agent,
        harbor_model=harbor_model,
        n_attempts=n_attempts,
        timeout_multiplier=timeout_multiplier,
        concurrency=concurrency,
        env_file=env_file,
        reward_gate=reward_gate,
        eval_timeout_s=eval_timeout_s,
        max_eval_workers=max_eval_workers,
        dry_run=dry_run,
        force=force,
        verify_patches=verify_patches,
    )
    result = runner.evaluate_candidate(
        candidate=candidate,
        candidate_id=DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        agent_name=DEFAULT_AUTOLAB_SCAFFOLD_NAME,
    )
    frontier_path = out_dir / "pareto_frontier.json"
    save_frontier(
        frontier_path,
        [
            ParetoPoint(
                candidate_id=result.candidate_id,
                scaffold_name=result.scaffold_name,
                passrate=result.passrate,
                token_consuming=result.token_consuming,
                avg_token_consuming=result.avg_token_consuming,
                average_score=result.average_score,
                result_path=result.result_path,
                config=result.config,
            )
        ],
        quality_gap_threshold=pareto_quality_threshold,
    )
    summary = {
        "benchmark": "autolab",
        "target_system": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        "split": split,
        "limit": limit,
        "count": len(tasks),
        "dry_run": dry_run,
        "force": force,
        "candidate_count": 1,
        "candidates": [result.to_dict()],
        "pareto_frontier_path": str(frontier_path),
    }
    (out_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


# ---------------------------------------------------------------------------
# Trial-tree parsing helpers.
# ---------------------------------------------------------------------------
def _collect_attempts(
    *,
    job_dir: Path,
    task_id: str,
    gate: float,
) -> list[AutolabAttempt]:
    """Walk harbor's trial dirs under ``job_dir`` and read each reward.

    The job-level ``result.json`` excludes per-trial rewards, so we read each
    trial's ``result.json`` (NOTE: the file is ``result.json`` despite the
    docstring in harbor's paths.py saying ``results.json``) and prefer the bare
    float ``verifier/reward.txt``.
    """

    attempts: list[AutolabAttempt] = []
    if not job_dir.is_dir():
        return attempts
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        result_file = trial_dir / "result.json"
        if not result_file.is_file():
            continue
        try:
            tr = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(tr.get("task_name") or "") != task_id:
            # Defensive: a single-task job dir should only hold this task.
            continue
        errored = tr.get("exception_info") is not None
        reward = _read_trial_reward(trial_dir, tr)
        if reward is None:
            reward, errored = 0.0, True
        agent_ctx = tr.get("agent_result") or {}
        attempts.append(
            AutolabAttempt(
                reward=reward,
                passed=(not errored) and reward >= gate,
                prompt_tokens=int(agent_ctx.get("n_input_tokens") or 0),
                completion_tokens=int(agent_ctx.get("n_output_tokens") or 0),
                errored=errored,
                trial_name=str(tr.get("trial_name") or trial_dir.name),
                trial_dir=str(trial_dir),
            )
        )
    return attempts


def _read_trial_reward(trial_dir: Path, trial_result: Mapping[str, Any]) -> float | None:
    """Reward for one trial: reward.txt → result.json → reward.json."""

    reward_txt = trial_dir / "verifier" / "reward.txt"
    reward_json = trial_dir / "verifier" / "reward.json"
    try:
        if reward_txt.is_file() and reward_txt.stat().st_size > 0:
            return float(reward_txt.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    verifier_result = trial_result.get("verifier_result")
    if isinstance(verifier_result, Mapping):
        rewards = verifier_result.get("rewards")
        if isinstance(rewards, Mapping) and rewards.get("reward") is not None:
            try:
                return float(rewards["reward"])
            except (TypeError, ValueError):
                pass
    try:
        if reward_json.is_file() and reward_json.stat().st_size > 0:
            data = json.loads(reward_json.read_text(encoding="utf-8"))
            if data.get("reward") is not None:
                return float(data["reward"])
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Candidate-dict → harbor flag rendering.
# ---------------------------------------------------------------------------
def _candidate_agent_kwargs(candidate: Mapping[str, Any]) -> dict[str, Any]:
    kwargs = candidate.get("agent_kwargs")
    if isinstance(kwargs, Mapping):
        # prompt_template is silently ignored by terminus-2; drop it so we don't
        # emit a misleading no-op flag.
        return {str(k): v for k, v in kwargs.items() if k != "prompt_template"}
    return {}


def _candidate_agent_env(candidate: Mapping[str, Any]) -> dict[str, str]:
    env = candidate.get("agent_env")
    if isinstance(env, Mapping):
        return {str(k): str(v) for k, v in env.items()}
    return {}


def _render_ak_value(value: Any) -> str:
    """Render an ``--ak`` value. Scalars pass through; containers as JSON.

    harbor's ``parse_kwargs`` coerces numbers/bools/lists/dicts from the
    string, so JSON-encoding non-strings round-trips correctly.
    """

    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Score breakdown (per-domain AND per-task_id buckets).
# ---------------------------------------------------------------------------
def _score_breakdown(task_results: list[TaskResult]) -> dict[str, dict[str, Any]]:
    """Per-task_id buckets only (no per-domain bucketing).

    Matches the per-task calibration design used for the agentic/OS domain: the
    proposer's prediction is graded per individual ``task_id``, never per
    category. We deliberately do NOT add ``domain::`` buckets — per-category
    aggregates invite category-level score bets, which the WMC protocol treats
    as near-random noise that drives the optimizer's curse.
    """

    n = len(task_results)
    breakdown: dict[str, dict[str, Any]] = {
        "all": {
            "count": n,
            "passrate": (sum(1 for t in task_results if t.passed) / n) if n else 0.0,
            "average_score": (sum(t.score for t in task_results) / n) if n else 0.0,
        }
    }
    for t in task_results:
        breakdown[t.task_id] = {
            "count": 1,
            "passrate": 1.0 if t.passed else 0.0,
            "average_score": float(t.score),
        }
    return breakdown


def _load_candidate_result(
    result_path: Path,
    *,
    candidate_id: str,
    agent_name: str,
    config: dict[str, Any],
) -> CandidateResult | None:
    if not result_path.exists():
        return None
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        candidate = CandidateResult.from_dict(payload["candidate"])
    except Exception:
        return None
    if (
        candidate.candidate_id != candidate_id
        or candidate.scaffold_name != agent_name
        or candidate.config != config
    ):
        return None
    return candidate


# ---------------------------------------------------------------------------
# Subprocess helpers (mirrors swebench's process-group kill pattern).
# ---------------------------------------------------------------------------
def _run_subprocess_with_timeout(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and kill its whole process group on timeout."""

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=extra_env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=stdout or exc.stdout,
            stderr=stderr or exc.stderr,
        ) from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
        proc.wait(timeout=2)
        return
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _timeout_output_to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
