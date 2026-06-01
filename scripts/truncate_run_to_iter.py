#!/usr/bin/env python3
"""Truncate a WorldCalib run back to a cutoff iteration (inclusive).

Removes every trace of iterations ``> cutoff`` from BOTH ledger dbs and the
on-disk per-iteration artifacts, so the run can be ``--resume``d cleanly from
``cutoff + 1`` with an uncontaminated ledger / world model:

  * ``runstore.db``        — the RunStore ledger (world_model_distiller +
                             critic ``proposal_outcomes`` base rate read it).
  * ``traces/index.db``    — the TraceHarness store (``trace_similar`` and the
                             other ``trace_*`` MCP tools read it; this is where
                             ``iteration_diffs`` lives).
  * ``candidate_results/`` — deleting ``iter>cutoff`` files is what actually
                             moves the resume start to ``cutoff + 1`` (the
                             optimizer derives ``max(completed)+1`` from here).
  * ``traces/spans``, ``traces/diagnostic`` — per-iteration bundles.
  * derived summaries (``world_model.md`` etc.) are removed so they are
    regenerated against the truncated ledger rather than the contaminated one.

``proposer_calls/iter_>cutoff`` and the ``iter>cutoff`` rows in
``evolution_summary.jsonl`` / ``diff_summary.jsonl`` are intentionally NOT
touched here — the optimizer's own ``_clean_stale_iteration_artifacts`` clears
them on ``--resume``.

Dry-run by default; pass ``--apply`` to actually delete.

Usage:
  python scripts/truncate_run_to_iter.py <run_dir> --cutoff 4          # preview
  python scripts/truncate_run_to_iter.py <run_dir> --cutoff 4 --apply  # execute
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

# ---- iteration extraction -------------------------------------------------

_DIR_ITER = re.compile(r"iter_?0*(\d+)")
# evidence_links ids look like "<run>:proposal:005:<cand>", ":mod:005",
# ":candidate:005:<cand>", ":call:005"; trace ids look like "iter005_...".
_ID_ITER = re.compile(r":(?:proposal|candidate|call|mod):0*(\d+)|iter0*(\d+)")


def _dir_iter(name: str) -> int | None:
    m = _DIR_ITER.search(name)
    return int(m.group(1)) if m else None


def _ids_max_iter(*ids: str) -> int | None:
    """Largest iteration number referenced across the given id strings, or None
    if none of them encode an iteration (run-level / file-level links)."""
    found: list[int] = []
    for s in ids:
        for m in _ID_ITER.finditer(s or ""):
            for g in m.groups():
                if g is not None:
                    found.append(int(g))
    return max(found) if found else None


# ---- db truncation --------------------------------------------------------


def _count(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def truncate_runstore(db_path: Path, cutoff: int, apply: bool) -> list[str]:
    report: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'"
        )}

        # Tables with a direct `iteration` column.
        direct = [
            "artifacts", "candidates", "eval_results", "iterations",
            "modifications", "modified_files", "proposal_outcomes",
            "proposals", "proposer_calls", "state_snapshots", "tool_accesses",
            "traces",
        ]
        for t in direct:
            if t not in tables:
                continue
            n = _count(conn, f"select count(*) from {t} where iteration > ?", (cutoff,))
            report.append(f"  runstore.{t}: -{n}")
            if apply and n:
                conn.execute(f"delete from {t} where iteration > ?", (cutoff,))

        # frontier_members: drop snapshots taken after cutoff as well as any
        # member row that belongs to a later iteration.
        if "frontier_members" in tables:
            n = _count(
                conn,
                "select count(*) from frontier_members "
                "where iteration > ? or as_of_iteration > ?",
                (cutoff, cutoff),
            )
            report.append(f"  runstore.frontier_members: -{n}")
            if apply and n:
                conn.execute(
                    "delete from frontier_members "
                    "where iteration > ? or as_of_iteration > ?",
                    (cutoff, cutoff),
                )

        # trace_diffs / trace_spans key off trace_id; a trace_id is stale iff
        # its trace row (already counted above) was for iteration > cutoff. We
        # must read the stale ids BEFORE deleting from `traces`, so compute via
        # the surviving set instead: delete rows whose trace_id is NOT among the
        # traces that remain (iteration <= cutoff).
        for t in ("trace_diffs", "trace_spans"):
            if t not in tables or "traces" not in tables:
                continue
            n = _count(
                conn,
                f"select count(*) from {t} where trace_id not in "
                "(select trace_id from traces where iteration <= ?)",
                (cutoff,),
            )
            report.append(f"  runstore.{t}: -{n}")
            if apply and n:
                conn.execute(
                    f"delete from {t} where trace_id not in "
                    "(select trace_id from traces where iteration <= ?)",
                    (cutoff,),
                )

        # evidence_links: drop any link that references an iteration > cutoff.
        if "evidence_links" in tables:
            stale = [
                r[0]
                for r in conn.execute(
                    "select link_id, source_id, target_id from evidence_links"
                ).fetchall()
                if (lambda mx: mx is not None and mx > cutoff)(
                    _ids_max_iter(r[1], r[2])
                )
            ]
            report.append(f"  runstore.evidence_links: -{len(stale)}")
            if apply and stale:
                conn.executemany(
                    "delete from evidence_links where link_id = ?",
                    [(lid,) for lid in stale],
                )

        if apply:
            conn.commit()
            conn.execute("vacuum")
    finally:
        conn.close()
    return report


def truncate_trace_index(db_path: Path, cutoff: int, apply: bool) -> list[str]:
    report: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "select name from sqlite_master where type='table'"
        )}
        for t in ("iteration_diffs", "iteration_meta", "file_modifications",
                  "traces", "diff_embeddings"):
            if t not in tables:
                continue
            n = _count(conn, f"select count(*) from {t} where iteration > ?", (cutoff,))
            report.append(f"  traces/index.{t}: -{n}")
            if apply and n:
                conn.execute(f"delete from {t} where iteration > ?", (cutoff,))

        # `diffs` keys off trace_id, mirroring runstore.trace_diffs.
        if "diffs" in tables and "traces" in tables:
            n = _count(
                conn,
                "select count(*) from diffs where trace_id not in "
                "(select trace_id from traces where iteration <= ?)",
                (cutoff,),
            )
            report.append(f"  traces/index.diffs: -{n}")
            if apply and n:
                conn.execute(
                    "delete from diffs where trace_id not in "
                    "(select trace_id from traces where iteration <= ?)",
                    (cutoff,),
                )
        if apply:
            conn.commit()
            conn.execute("vacuum")
    finally:
        conn.close()
    return report


# ---- filesystem truncation ------------------------------------------------


def truncate_files(run_dir: Path, cutoff: int, apply: bool) -> list[str]:
    import shutil

    report: list[str] = []

    # candidate_results/iter<N>*.json — this is what moves the resume start.
    cr = run_dir / "candidate_results"
    if cr.is_dir():
        victims = [
            p for p in cr.iterdir()
            if p.is_file() and (_dir_iter(p.name) or 0) > cutoff
        ]
        report.append(
            f"  candidate_results/: -{len(victims)} files "
            f"({', '.join(sorted(p.name.split('_')[0] for p in victims)) or 'none'})"
        )
        if apply:
            for p in victims:
                p.unlink()

    # traces/spans/iter_<N>, traces/diagnostic/iter_<N>.md
    for sub in ("spans", "diagnostic"):
        d = run_dir / "traces" / sub
        if not d.is_dir():
            continue
        victims = [c for c in d.iterdir() if (_dir_iter(c.name) or 0) > cutoff]
        report.append(f"  traces/{sub}/: -{len(victims)}")
        if apply:
            for c in victims:
                shutil.rmtree(c) if c.is_dir() else c.unlink()

    # Derived summaries: remove so they regenerate against the truncated
    # ledger. world_model.md / calibration_track_record.md are read by the
    # proposer at step 0; the rest are rebuilt post-eval.
    derived = [
        "world_model.md", "calibration_track_record.md",
        "best_candidates.json", "candidate_score_table.json",
        "iteration_index.json", "retrieval_diagnostics_summary.json",
    ]
    removed = [f for f in derived if (run_dir / f).exists()]
    report.append(f"  derived summaries removed: {removed}")
    if apply:
        for f in removed:
            (run_dir / f).unlink()

    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--cutoff", type=int, required=True,
                    help="keep iterations <= cutoff; drop everything after")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: dry-run preview)")
    args = ap.parse_args()

    run_dir: Path = args.run_dir
    runstore = run_dir / "runstore.db"
    trace_index = run_dir / "traces" / "index.db"

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== truncate {run_dir} to iter <= {args.cutoff}  [{mode}] ===")

    if runstore.exists():
        print("runstore.db:")
        for line in truncate_runstore(runstore, args.cutoff, args.apply):
            print(line)
    if trace_index.exists():
        print("traces/index.db:")
        for line in truncate_trace_index(trace_index, args.cutoff, args.apply):
            print(line)
    print("filesystem:")
    for line in truncate_files(run_dir, args.cutoff, args.apply):
        print(line)

    if not args.apply:
        print("\n(dry-run — nothing changed. re-run with --apply to execute.)")
    else:
        print("\nDONE. Now regenerate world_model.md + resume from cutoff+1.")


if __name__ == "__main__":
    main()
