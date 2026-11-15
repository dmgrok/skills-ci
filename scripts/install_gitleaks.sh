#!/usr/bin/env bash
# Install gitleaks 8.30.1 and check the archive against the release checksums.
set -euo pipefail

version=8.30.1
case "$(uname -m)" in
  x86_64)
    archive="gitleaks_${version}_linux_x64.tar.gz"
    sum=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    ;;
  aarch64|arm64)
    archive="gitleaks_${version}_linux_arm64.tar.gz"
    sum=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080
    ;;
  *)
    echo "unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

url="https://github.com/gitleaks/gitleaks/releases/download/v${version}/${archive}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$archive" "$url"
echo "${sum}  $tmp/$archive" | sha256sum -c -
tar -xzf "$tmp/$archive" -C "$tmp" gitleaks
install_dir="${HOME}/.local/bin"
mkdir -p "$install_dir"
install -m 0755 "$tmp/gitleaks" "$install_dir/gitleaks"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$install_dir" >> "$GITHUB_PATH"
fi
"$install_dir/gitleaks" version
