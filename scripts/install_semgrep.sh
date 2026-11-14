#!/usr/bin/env bash
# Install Semgrep CE 1.185.0 from the manylinux wheel and check its sha256.
# The wheel is the open-source engine. pip then installs that wheel's
# dependencies from PyPI; those dependencies are not each checksum-pinned.
set -euo pipefail

version=1.185.0
case "$(uname -m)" in
  x86_64)
    wheel="semgrep-${version}-cp310.cp311.cp312.cp313.cp314.py310.py311.py312.py313.py314-none-manylinux_2_34_x86_64.whl"
    sum=0eb6aaadad5b957af96d1300487e10af1dc8016e8ef53072effb48cd4906c02b
    url="https://files.pythonhosted.org/packages/f2/13/0d4dc8d124794105f300082c46e3d8ad45eac7af63113b57a5966629b5a3/${wheel}"
    ;;
  aarch64|arm64)
    wheel="semgrep-${version}-cp310.cp311.cp312.cp313.cp314.py310.py311.py312.py313.py314-none-manylinux_2_34_aarch64.whl"
    sum=8cffbaf80abb8e39abc6d7a86588dcf94b7ddc1f40e8e16e555a1116347be3ef
    url="https://files.pythonhosted.org/packages/ba/4e/cae05468e1b8c33a18bafb25539f845d6f35e6e58973ebdd2aafa6b387ed/${wheel}"
    ;;
  *)
    echo "unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$wheel" "$url"
echo "${sum}  $tmp/$wheel" | sha256sum -c -

venv="${HOME}/.local/semgrep-venv"
rm -rf "$venv"
python3 -m venv "$venv"
"$venv/bin/pip" install --disable-pip-version-check "$tmp/$wheel"
install_dir="${HOME}/.local/bin"
mkdir -p "$install_dir"
ln -sfn "$venv/bin/semgrep" "$install_dir/semgrep"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$install_dir" >> "$GITHUB_PATH"
fi
export PATH="$install_dir:$PATH"
semgrep --version
