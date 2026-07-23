"""Portable runtime and package-resource path helpers."""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any


def runtime_root(explicit: Path | str | None = None) -> Path:
    """Resolve the run root from an explicit value, env, or current directory."""

    raw = explicit or os.environ.get("WORLDCALIB_WORKDIR") or Path.cwd()
    return Path(raw).expanduser().resolve()


def resolve_external_path(
    explicit: Path | str | None,
    *,
    env_var: str,
    label: str,
    must_exist: bool = True,
) -> Path:
    """Resolve an external checkout or dataset without inspecting source paths."""

    raw = explicit or os.environ.get(env_var)
    if not raw:
        raise ValueError(f"{label} is required; pass a CLI path or set {env_var}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = runtime_root() / path
    path = path.resolve()
    if must_exist and not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def package_text(package: str, name: str) -> str:
    """Read a UTF-8 package resource."""

    return files(package).joinpath(name).read_text(encoding="utf-8")


def package_json(package: str, name: str) -> Any:
    """Read a JSON package resource."""

    return json.loads(package_text(package, name))


def package_file(package: str, name: str) -> Path:
    """Return a physical package file path for subprocess/file-copy consumers."""

    resource = files(package).joinpath(name)
    path = Path(str(resource))
    if not path.is_file():
        raise FileNotFoundError(f"package resource is not a physical file: {package}:{name}")
    return path
