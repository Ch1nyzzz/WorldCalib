#!/bin/bash
# Apply AutoLab's three harbor patches to the cyh_dev venv that WorldCalib's
# autolab domain shells out to. AutoLab ships third_party/autolab/harbor_patch.sh
# but it hard-codes "$SCRIPT_DIR/.venv"; the canonical harbor here lives in a
# different venv, so we re-target it. All three patches are idempotent (each
# detects already-applied state).
#
#   Patch 1: terminus-2 single-command duration ceiling 60s -> 1200s
#            (long builds/benchmarks otherwise get truncated at 60s).
#   Patch 2: DockerEnvironment.supports_gpus False -> True
#            (without it the 12 gpus=1 tasks — model_development + cuda — refuse
#            to run at all).
#   Patch 3: HARBOR_GPU_DEVICES env -> temp compose override pinning
#            NVIDIA_VISIBLE_DEVICES (so a trial can be pinned to specific H100s).
#
# Usage:
#   bash scripts/apply_harbor_patch_cyh_dev.sh                  # patch cyh_dev
#   VENV_PYTHON=/path/to/venv/bin/python bash scripts/apply_harbor_patch_cyh_dev.sh
#
# Verify afterwards:
#   python -c "from worldcalib.autolab.autolab import verify_harbor_patched as v; print(v() or 'PATCHED')"
set -euo pipefail

VENV_PYTHON="${VENV_PYTHON:-/data/home/yuhan/cyh_dev/bin/python}"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: VENV_PYTHON not executable: $VENV_PYTHON" >&2
    exit 1
fi

VENV_SITE=$("$VENV_PYTHON" -c "import sysconfig; print(sysconfig.get_path('purelib'))")
echo "Patching harbor in: $VENV_SITE"

# ── Patch 1: terminus-2 max duration 60 -> 1200 seconds ──
"$VENV_PYTHON" -c "
from pathlib import Path
p = Path('$VENV_SITE/harbor/agents/terminus_2/terminus_2.py')
s = p.read_text()
old = 'duration_sec=min(parsed_cmd.duration, 60),'
new = 'duration_sec=min(parsed_cmd.duration, 1200),'
if old in s:
    p.write_text(s.replace(old, new, 1)); print('patched terminus_2 max duration: 60 -> 1200')
elif new in s:
    print('terminus_2 max duration already patched')
else:
    raise SystemExit('terminus_2 duration pattern not found and not already patched')
"

# ── Patch 2: docker environment GPU support ──
"$VENV_PYTHON" -c "
from pathlib import Path
p = Path('$VENV_SITE/harbor/environments/docker/docker.py')
s = p.read_text()
old = '    def supports_gpus(self) -> bool:\n        return False'
new = '    def supports_gpus(self) -> bool:\n        return True'
if old in s:
    p.write_text(s.replace(old, new, 1)); print('patched docker GPU support: False -> True')
elif new in s:
    print('docker GPU support already patched')
else:
    raise SystemExit('docker GPU pattern not found and not already patched')
"

# ── Patch 3: GPU device selection via HARBOR_GPU_DEVICES env var ──
VENV_SITE="$VENV_SITE" "$VENV_PYTHON" << 'PYEOF'
from pathlib import Path
import os, textwrap

p = Path(f"{os.environ['VENV_SITE']}/harbor/environments/docker/docker.py")
s = p.read_text()
marker = "# PATCH: GPU device selection"
if marker in s:
    print("GPU device selection already patched")
else:
    old_method = "    @property\n    def _docker_compose_paths(self) -> list[Path]:"
    if old_method not in s:
        print("WARNING: could not find _docker_compose_paths property; skipping patch 3")
    else:
        helper = textwrap.dedent('''\
    # PATCH: GPU device selection
    def _gpu_override_compose_path(self) -> "Path | None":
        """Generate a temp compose override to pin specific GPU devices."""
        gpu_devices = os.environ.get("HARBOR_GPU_DEVICES")
        if not gpu_devices:
            return None
        import tempfile
        content = f"""services:
  main:
    runtime: nvidia
    environment:
      NVIDIA_VISIBLE_DEVICES: "{gpu_devices}"
    deploy:
      resources:
        reservations:
          devices: !reset []
"""
        tmp = Path(tempfile.mktemp(suffix="-gpu-override.yaml", prefix="harbor-"))
        tmp.write_text(content)
        return tmp

''')
        s = s.replace(old_method, helper + "    " + old_method.lstrip())
        old_return = "        return paths"
        new_return = ("        # PATCH: GPU device override\n"
                      "        _gpu_ov = self._gpu_override_compose_path()\n"
                      "        if _gpu_ov:\n"
                      "            paths.append(_gpu_ov)\n\n"
                      "        return paths")
        idx = s.rfind(old_return)
        if idx != -1:
            s = s[:idx] + new_return + s[idx + len(old_return):]
            p.write_text(s)
            print("patched GPU device selection: use HARBOR_GPU_DEVICES env var")
        else:
            print("WARNING: could not find 'return paths'; skipping patch 3")
PYEOF

echo "done. verify with: python -c \"from worldcalib.autolab.autolab import verify_harbor_patched as v; print(v() or 'PATCHED')\""
