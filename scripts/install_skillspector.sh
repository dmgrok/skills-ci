#!/usr/bin/env bash
# Install SkillSpector 2.13.4 from the commit tagged v2.13.4.
# The package requires Python >=3.12,<3.15. This script requires 3.12,
# the interpreter the constraint file was resolved with.
set -euo pipefail

sha=54824463814a0be01360792523ec7245a69190fc
expected_version=2.13.4

python3_bin=$(command -v python3)
echo "using ${python3_bin}"
python_version=$("$python3_bin" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if [ "$python_version" != "3.12" ]; then
  echo "SkillSpector constraints are pinned for CPython 3.12; found $python_version at $python3_bin" >&2
  exit 1
fi

script_dir=$(cd "$(dirname "$0")" && pwd)
constraints="$script_dir/../requirements-skillspector.txt"
if [ ! -f "$constraints" ]; then
  echo "missing $constraints" >&2
  exit 1
fi

venv="${HOME}/.local/skillspector-venv"
rm -rf "$venv"
"$python3_bin" -m venv "$venv"
export GIT_TERMINAL_PROMPT=0
"$venv/bin/python" -m pip install --disable-pip-version-check \
  --constraint "$constraints" \
  "skillspector @ git+https://github.com/NVIDIA/SkillSpector.git@${sha}"

"$venv/bin/python" - "$sha" "$expected_version" <<'PY'
import importlib.metadata as metadata
import json
import sys

sha = sys.argv[1]
expected = sys.argv[2]
version = metadata.version("skillspector")
if version != expected:
    raise SystemExit("expected skillspector %s, found %s" % (expected, version))
dist = metadata.distribution("skillspector")
direct_text = dist.read_text("direct_url.json")
if not direct_text:
    raise SystemExit("skillspector install has no direct_url.json")
direct = json.loads(direct_text)
commit = (direct.get("vcs_info") or {}).get("commit_id", "")
if commit != sha:
    raise SystemExit("expected commit %s, found %s" % (sha, commit or direct))
print("skillspector %s %s" % (version, commit))
PY

install_dir="${HOME}/.local/bin"
mkdir -p "$install_dir"
ln -sfn "$venv/bin/skillspector" "$install_dir/skillspector"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$install_dir" >> "$GITHUB_PATH"
fi
export PATH="$install_dir:$PATH"
skillspector --version | grep -F "SkillSpector v${expected_version}"
