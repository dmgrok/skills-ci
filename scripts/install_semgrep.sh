#!/usr/bin/env bash
# Install Semgrep CE 1.185.0 and its transitive dependencies from
# requirements-semgrep.txt. Every distribution is hash-pinned for
# CPython 3.14 on manylinux x86_64, which is what ubuntu-latest used
# when this lock was made. pip install --require-hashes checks them.
set -euo pipefail

if [ "$(uname -m)" != "x86_64" ]; then
  echo "requirements-semgrep.txt is pinned for x86_64; found $(uname -m)" >&2
  exit 1
fi

python_version=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if [ "$python_version" != "3.14" ]; then
  echo "requirements-semgrep.txt is pinned for CPython 3.14; found $python_version" >&2
  exit 1
fi

script_dir=$(cd "$(dirname "$0")" && pwd)
requirements="$script_dir/../requirements-semgrep.txt"
if [ ! -f "$requirements" ]; then
  echo "missing $requirements" >&2
  exit 1
fi

venv="${HOME}/.local/semgrep-venv"
rm -rf "$venv"
python3 -m venv "$venv"
"$venv/bin/python" -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r "$requirements"
install_dir="${HOME}/.local/bin"
mkdir -p "$install_dir"
ln -sfn "$venv/bin/semgrep" "$install_dir/semgrep"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$install_dir" >> "$GITHUB_PATH"
fi
export PATH="$install_dir:$PATH"
semgrep --version
