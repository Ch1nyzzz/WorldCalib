"""Build the per-iteration proposer assignment.

Static benchmark contracts live in package prompt resources. This module only
describes the current iteration, staged evidence, editable paths, and required
candidate JSON.
"""

from __future__ import annotations

from pathlib import Path


_EXTERNAL_SOURCE_DIRS = {
    "appworld_passthrough": "appworld",
    "toolathlon_passthrough": "toolathlon",
    "terminus2_tb2": "terminus2_agent_tb2",
}


def _optimization_subject(target_system: str) -> str:
    return {
        "appworld_passthrough": "AppWorld code-agent policy",
        "toolathlon_passthrough": "Toolathlon tool-use policy",
        "terminus2_tb2": "Terminal-Bench 2.0 terminal-agent harness",
        "agent": "agent policy",
    }.get(target_system.lower(), "memory or agent scaffold")


def _candidate_scaffold_name(target_system: str) -> str:
    normalized = target_system.lower()
    if normalized in _EXTERNAL_SOURCE_DIRS or normalized.endswith("_source"):
        return target_system
    return f"{target_system}_source"


def _editable_source_path(source_snapshot_dir: Path, target_system: str) -> Path:
    external = _EXTERNAL_SOURCE_DIRS.get(target_system.lower())
    if external:
        return source_snapshot_dir / "candidate" / "upstream_source" / external
    return source_snapshot_dir / "candidate" / "project_source"


def build_progressive_proposer_prompt(
    *,
    run_id: str,
    iteration: int,
    run_dir: Path,
    pending_eval_path: Path,
    summaries_dir: Path,
    include_summaries: bool = True,
    reference_iterations_dir: Path,
    generated_dir: Path,
    source_snapshot_dir: Path,
    budget: str,
    reference_iterations: tuple[int, ...],
    target_system: str,
    optimization_directions: tuple[str, ...],
    split: str,
    limit: int,
    selection_policy: str = "self",
    benchmark_name: str = "LOCOMO conversational-memory QA",
    current_base_iter: int | None = None,
    current_base_passrate: float | None = None,
    current_base_average_score: float | None = None,
    trace_harness_dir: Path | None = None,
) -> str:
    """Return the user-message assignment for one proposer invocation."""

    workspace_dir = run_dir

    def show(path: Path) -> str:
        try:
            return str(path.relative_to(workspace_dir))
        except ValueError:
            return str(path)

    refs = ", ".join(f"iter_{item:03d}" for item in reference_iterations) or "none"
    refs_json = ", ".join(str(item) for item in reference_iterations)
    pending = show(pending_eval_path)
    summaries = show(summaries_dir)
    references = show(reference_iterations_dir)
    snapshot = show(source_snapshot_dir)
    generated = show(generated_dir)
    editable = show(_editable_source_path(source_snapshot_dir, target_system))

    if include_summaries:
        summary_assignment = f"- Cumulative summaries: {summaries}/"
        summary_files = (
            f"- {summaries}/evolution_summary.jsonl — full event history through "
            "the previous iteration.\n"
            f"- {summaries}/best_candidates.json — current quality frontier."
        )
    else:
        summary_assignment = "- Cumulative summaries: not provided in this run."
        summary_files = (
            f"- No cumulative summaries; inspect {references}/iter_NNN/ directly."
        )

    if current_base_iter is not None:
        metrics = ""
        if current_base_passrate is not None:
            metrics = f" (passrate {current_base_passrate:.4f}"
            if current_base_average_score is not None:
                metrics += f", average_score {current_base_average_score:.4f}"
            metrics += ")"
        if selection_policy == "self":
            starting_point = f"""## Starting point

The default patch base is iter_{current_base_iter:03d}{metrics}, already staged
under {snapshot}/candidate/. Inspect frontier_manifest.json and
task_score_matrix.json before choosing a parent. You may keep this base, replace
it with a previous source snapshot, or graft mechanisms across prior snapshots.
Declare the parent you actually used as base_iter in the candidate."""
        else:
            starting_point = f"""## Starting point

Edit the staged iter_{current_base_iter:03d}{metrics} source under
{snapshot}/candidate/."""
    elif selection_policy == "self":
        starting_point = f"""## Starting point

No prior candidate beats the seed. Start from {snapshot}/candidate/ or choose a
previous snapshot after reading frontier_manifest.json and task_score_matrix.json.
Declare base_iter as 0 for the clean seed or the selected prior iteration."""
    else:
        starting_point = f"""## Starting point

Every iteration starts from the clean source under {snapshot}/candidate/.
Historical iterations are diagnostic references only."""

    focus = ""
    if optimization_directions:
        focus = "\n## Optional mechanism directions\n\n" + "\n".join(
            f"- {item}" for item in optimization_directions
        )

    trace_files = ""
    if trace_harness_dir is not None:
        traces = show(trace_harness_dir)
        trace_files = f"""
- {traces}/manifest.json — trace schema and benchmark metadata.
- {traces}/diagnostic/iter_NNN.md — regression, persistent-failure, and
  breakthrough summaries.
- {traces}/spans/iter_NNN/<candidate>.jsonl — full structured task traces."""

    external = _EXTERNAL_SOURCE_DIRS.get(target_system.lower())
    if external:
        edit_scope = (
            f"The primary editable policy is {editable}/. Project source under "
            f"{snapshot}/candidate/project_source/src/worldcalib/ is context and "
            "harness code unless the benchmark skill explicitly permits an edit."
        )
    else:
        edit_scope = (
            f"Edit package source under {editable}/src/worldcalib/ and optional "
            f"wrapper modules under {generated}/."
        )

    candidate_name = _candidate_scaffold_name(target_system)
    subject = _optimization_subject(target_system)
    return f"""# WorldCalib proposer — iteration {iteration}

You are optimizing the {subject} for {benchmark_name}.

## Assignment

- Run id: {run_id}
- Target system: {target_system}
- Budget: {budget}
- Eval split: {split}
- Eval limit: {limit} (0 means the full split)
{summary_assignment}
- Raw reference iterations: {references}/ ({refs})
- Editable source: {editable}/
- Optional generated modules: {generated}/
- Required output: {pending}

{starting_point}
{focus}

## Evidence available

{summary_files}
- {references}/ — raw prior iteration bundles, including diffs, evaluations,
  task evidence, and source snapshots.
- {snapshot}/candidate/ — the active editable snapshot.
- {snapshot}/candidate/original_project_source/ — clean source for diffing.
{trace_files}

## Edit scope

{edit_scope}
Write only under {snapshot}/candidate/**, {generated}/**, and {pending}.

## Required output

Write exactly one candidate to {pending} with this JSON shape:

{{
  "candidates": [
    {{
      "name": "short_unique_name",
      "scaffold_name": "{candidate_name}",
      "top_k": 8,
      "window": 1,
      "source_family": "{target_system}",
      "reference_iterations": [{refs_json}],
      "build_tag": "stable_build_identifier",
      "source_snapshot_path": "{snapshot}",
      "base_iter": 0,
      "extra": {{
        "source_project_path": "{editable}"
      }},
      "hypothesis": "mechanistic reason this should improve the objective",
      "generalization_evidence": "failure family and at least two evidence sources",
      "counterexample_audit": "already-correct behavior this should not harm",
      "changes": "brief implementation summary"
    }}
  ]
}}
"""
