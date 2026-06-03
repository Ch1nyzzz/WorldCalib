"""Generic dynamic loading for candidate agent scaffolds.

The shared body of the two per-backend loaders (``agent_dynamic`` for
agentbench, ``tau2_dynamic`` for tau2): given pending_eval candidate metadata it
instantiates a scaffold object, reusing the isolation and module helpers from
``dynamic`` so source-backed candidates (an edited scaffold tree under a
workspace snapshot) import from the copied tree instead of the host package.

Backends parameterize this with their own registry builder, source-class map,
default seed key, and type check; the control flow (source-backed edited
scaffold → built-in registry → dynamic module/class/factory/build_scaffold/
SCAFFOLD_CLASS) is identical across backends and lives here once.

Kept ``agentrl`` / ``tau2`` free: it imports neither at module top level, so the
tau2 backend can route through it without pulling in agentrl.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from worldcalib.dynamic import (
    _candidate_root,
    _isolated_memomemo_project,
    _load_module_path,
    _source_project_path,
)


def load_candidate_selfdistill_scaffold(
    candidate: dict[str, Any],
    *,
    project_root: Path,
    registry_build: Callable[[str], object],
    source_classes: dict[str, tuple[str, str]],
    default_seed: str,
    is_compatible: Callable[[object], bool],
) -> object:
    """Instantiate an agent scaffold from pending_eval candidate metadata.

    Args:
        candidate: pending_eval candidate metadata.
        project_root: repo root used to resolve ``src`` and snapshot paths.
        registry_build: builds a built-in scaffold by name.
        source_classes: scaffold_name -> (module, class) inside the snapshot.
        default_seed: key into ``source_classes`` used as the fallback when the
            candidate's ``scaffold_name`` is not a known source-backed scaffold.
        is_compatible: type check; the produced object is rejected (``TypeError``)
            when this returns ``False``.
    """

    def _check(obj: object, origin: str) -> object:
        if not is_compatible(obj):
            raise TypeError(f"{origin} did not produce a compatible scaffold object")
        return obj

    src_path = str(project_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    candidate_root = _candidate_root(candidate, project_root=project_root)
    if candidate_root is not None:
        root_path = str(candidate_root)
        if root_path not in sys.path:
            sys.path.insert(0, root_path)

    source_project_path = _source_project_path(candidate, project_root=project_root)
    scaffold_name = candidate.get("scaffold_name") or candidate.get("seed_name")

    module_path = str(candidate.get("module_path") or "").strip()
    module_name = str(candidate.get("module") or "").strip()
    class_name = str(candidate.get("class") or "").strip()
    factory_name = str(candidate.get("factory") or "").strip()

    # source-backed edited scaffold (proposer edited the scaffold tree in the snapshot)
    if scaffold_name and source_project_path is not None and not (module_name or module_path):
        mod, cls = source_classes.get(str(scaffold_name), source_classes[default_seed])
        with _isolated_memomemo_project(source_project_path):
            importlib.invalidate_caches()
            module = importlib.import_module(mod)
            obj = getattr(module, cls)()
        return _check(obj, f"{mod}.{cls}")

    # built-in registry
    if scaffold_name and not (module_name or module_path):
        return registry_build(str(scaffold_name))

    if not (module_name or module_path):
        raise ValueError(
            "agentic candidate must provide `scaffold_name`, `module`, or `module_path`"
        )

    # dynamic module / class / factory (optionally isolated from a snapshot)
    importlib.invalidate_caches()
    context = (
        _isolated_memomemo_project(source_project_path)
        if source_project_path is not None
        else nullcontext()
    )
    with context:
        if module_path:
            module = _load_module_path(module_path, project_root=project_root)
        else:
            if candidate_root is not None and module_name.startswith("worldcalib.generated."):
                module_name = module_name.removeprefix("worldcalib.generated.")
            if candidate_root is not None and module_name in sys.modules:
                del sys.modules[module_name]
            module = importlib.import_module(module_name)
            module = importlib.reload(module)

        if class_name:
            obj = getattr(module, class_name)()
        elif factory_name:
            obj = getattr(module, factory_name)()
        elif hasattr(module, "build_scaffold"):
            obj = module.build_scaffold()
        elif hasattr(module, "SCAFFOLD_CLASS"):
            obj = module.SCAFFOLD_CLASS()
        else:
            raise ValueError(
                f"{module_name or module_path} must expose class/factory/build_scaffold/SCAFFOLD_CLASS"
            )

    return _check(obj, module_name or module_path)
