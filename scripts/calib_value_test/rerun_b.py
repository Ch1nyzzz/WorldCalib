"""Re-run the proposer (kimi-k2.6, prediction-only) for condition B.

Faithfully replays the original proposer invocation — same claude CLI, same
kimi endpoint, same docker sandbox as
``scripts/launch_wmc_default_nosummary.sh`` — but against the staged scratch
workspace (LOO+redacted calibration, pinned candidate) and with the
prediction-only user prompt. The only intended variable vs condition A is the
calibration content.

Prereqs: stage.py has been run, and the environment carries KIMI_API_KEY /
OPENAI_API_KEY / DEEPSEEK_API_KEY. Launch with the project .env sourced:

    set -a && source .env && set +a
    python scripts/calib_value_test/rerun_b.py --iters 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import common as c  # noqa: E402
from worldcalib.claude_runner import (  # noqa: E402
    DEFAULT_DOCKER_ENV_VARS,
    ProposerSandboxConfig,
    run_claude_prompt,
)

from stage import OUT_ROOT, SCRATCH_ROOT  # noqa: E402

_PRINT_LOCK = threading.Lock()


def _log(msg: str) -> None:
    with _PRINT_LOCK:
        print(msg, flush=True)


KIMI_MODEL = "kimi-k2.6"
DOCKER_IMAGE = "docker-claude-kimi:latest"
DOCKER_HOME = "/tmp"
# Extra env vars the launcher exports + forwards into the proposer container,
# on top of claude_runner's DEFAULT_DOCKER_ENV_VARS.
_EXTRA_DOCKER_ENV = (
    "KIMI_API_KEY",
    "ENABLE_TOOL_SEARCH",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)


def _prepare_process_env() -> None:
    """Mirror the launcher's exports so docker -e passthrough finds them and
    every model alias the CLI might emit resolves to kimi-k2.6."""
    os.environ.setdefault("ENABLE_TOOL_SEARCH", "false")
    for var in (
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        os.environ[var] = KIMI_MODEL
    # Embeddings: let the OpenAI SDK use its defaults (official endpoint).
    os.environ.pop("DIFF_EMBEDDING_MODEL", None)
    os.environ.pop("OPENAI_BASE_URL", None)


def _kimi_base_url() -> str:
    key = os.environ.get("KIMI_API_KEY", "")
    if key.startswith("sk-kimi-"):
        return os.environ.get("KIMI_BASE_URL", "https://api.kimi.com/coding")
    return os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/anthropic")


def _docker_user() -> str:
    return f"{os.getuid()}:{os.getgid()}"


def rerun_iter(run: Path, n: int, timeout_s: int, condition: str = "B") -> dict:
    cond = condition.upper()
    ws_name = "workspace" if cond == "B" else f"workspace_{cond}"
    ws = SCRATCH_ROOT / f"iter_{n:03d}" / ws_name
    if not ws.is_dir():
        raise FileNotFoundError(f"scratch workspace missing; run stage.py first: {ws}")
    out_dir = OUT_ROOT / f"iter_{n:03d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = (ws / f"prompt_{cond}.md").read_text()
    skill = (ws / "PROPOSER_SKILL.md").read_text()

    sandbox = ProposerSandboxConfig(
        kind="docker",
        docker_image=DOCKER_IMAGE,
        docker_workspace="/workspace",
        docker_env_vars=DEFAULT_DOCKER_ENV_VARS + _EXTRA_DOCKER_ENV,
        docker_mounts=(f"{run.resolve()}/runstore.db:/runstore/runstore.db:ro",),
        docker_user=_docker_user(),
        docker_home=DOCKER_HOME,
    )

    # Ensure a clean slate: drop any prediction.md left from a prior attempt.
    (ws / "prediction.md").unlink(missing_ok=True)

    _log(f"[iter_{n:03d}/{cond}] launching kimi prediction-only re-run (timeout {timeout_s}s)…")
    result = run_claude_prompt(
        prompt,
        cwd=ws,
        log_dir=out_dir / f"agent_{cond}",
        name=f"proposer_{cond.lower()}",
        model=KIMI_MODEL,
        effort="max",
        timeout_s=timeout_s,
        sandbox=sandbox,
        base_url=_kimi_base_url(),
        auth_token=os.environ.get("KIMI_API_KEY", ""),
        append_system_prompt=skill,
    )

    pred_path = ws / "prediction.md"
    wrote = pred_path.is_file() and pred_path.read_text().strip() != ""
    if wrote:
        (out_dir / f"prediction_{cond}.md").write_text(pred_path.read_text())

    status = {
        "iter": n,
        "condition": cond,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "rate_limited": result.rate_limited,
        "duration_s": round(result.duration_s, 1),
        f"wrote_prediction_{cond}": wrote,
        "metrics": result.metrics,
    }
    (out_dir / f"rerun_{cond}_status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))
    _log(f"[iter_{n:03d}/{cond}] done: wrote_prediction_{cond}={wrote} rc={result.returncode} "
         f"timed_out={result.timed_out} rate_limited={result.rate_limited} dur={status['duration_s']}s")
    if not wrote:
        _log(f"[iter_{n:03d}/{cond}] WARNING: no prediction_{cond}.md produced. "
             f"stderr tail:\n{(result.stderr or '')[-800:]}")
    return status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(c.DEFAULT_RUN))
    ap.add_argument("--iters", default=",".join(str(i) for i in c.PILOT_ITERS))
    ap.add_argument("--timeout-s", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=1,
                    help="number of iters to re-run concurrently (parallel docker/kimi sessions)")
    ap.add_argument("--condition", default="B", choices=["B", "C"],
                    help="which counterfactual arm to re-run (B = LOO final calibration, "
                         "C = empty/zero-WMC baseline)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip iters that already have a non-empty prediction_{condition}.md")
    args = ap.parse_args()

    if not os.environ.get("KIMI_API_KEY"):
        sys.exit("fatal: KIMI_API_KEY not set; run `set -a && source .env && set +a` first.")
    _prepare_process_env()

    cond = args.condition.upper()
    run = Path(args.run)
    iters = [int(x) for x in args.iters.split(",") if x.strip()]
    if args.skip_existing:
        kept = []
        for n in iters:
            pb = OUT_ROOT / f"iter_{n:03d}" / f"prediction_{cond}.md"
            if pb.is_file() and pb.read_text().strip():
                _log(f"[iter_{n:03d}/{cond}] skip-existing: prediction_{cond}.md present")
            else:
                kept.append(n)
        iters = kept
    _log(f"kimi base_url = {_kimi_base_url()}  model = {KIMI_MODEL}  image = {DOCKER_IMAGE}")
    _log(f"re-running condition {cond} for {len(iters)} iters with {args.workers} workers: {iters}")

    wrote_key = f"wrote_prediction_{cond}"
    summary: list[dict] = []
    if args.workers <= 1:
        summary = [rerun_iter(run, n, args.timeout_s, cond) for n in iters]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(rerun_iter, run, n, args.timeout_s, cond): n for n in iters}
            for fut in as_completed(futs):
                n = futs[fut]
                try:
                    summary.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    _log(f"[iter_{n:03d}/{cond}] ERROR: {exc!r}")
                    summary.append({"iter": n, "error": repr(exc), wrote_key: False})

    summary.sort(key=lambda s: s.get("iter", 0))
    _log("\n=== rerun summary ===")
    for s in summary:
        _log(json.dumps({k: s.get(k) for k in ("iter", wrote_key, "returncode",
                                               "timed_out", "rate_limited", "duration_s", "error")},
                        ensure_ascii=False))
    n_ok = sum(1 for s in summary if s.get(wrote_key))
    _log(f"\n{n_ok}/{len(summary)} produced prediction_{cond}.md")


if __name__ == "__main__":
    main()
