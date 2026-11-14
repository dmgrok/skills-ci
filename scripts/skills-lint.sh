#!/usr/bin/env bash
# Strict skill-validator check used by the reusable Skill CI workflow.
# Requires skill-validator v1.8.0 on PATH. See docs/skills-ci.md.
#
# With no arguments, checks skills/ in this repository against
# scripts/skills-lint-allowlist.json. Callers of the reusable workflow
# pass --root, --skills-dir, and --allowlist.
set -euo pipefail

script_root=$(cd "$(dirname "$0")/.." && pwd)
target_root="$script_root"
skills_dir="skills"
allowlist=""
use_allowlist=0

usage() {
  echo "usage: skills-lint.sh [--root dir] [--skills-dir dir] [--allowlist file]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      target_root="${2:-}"
      shift 2
      ;;
    --skills-dir)
      skills_dir="${2:-}"
      shift 2
      ;;
    --allowlist)
      use_allowlist=1
      allowlist="${2:-}"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

if [[ -z "$target_root" || -z "$skills_dir" ]]; then
  usage
fi

if ! command -v skill-validator >/dev/null 2>&1; then
  echo "skill-validator is not on PATH. Install v1.8.0 as described in docs/skills-ci.md." >&2
  exit 1
fi

version=$(skill-validator --version)
if ! printf '%s\n' "$version" | grep -q 'v1.8.0'; then
  echo "expected skill-validator v1.8.0, found: $version" >&2
  exit 1
fi

# Companion files sit beside SKILL.md (html-email-report, ui-design).
# ui-design keeps agents/ and reference/ next to the spec's references/.
# Orphan checks are off because ui-design ships license and provenance
# files that the skill text does not link.
args=(
  check
  --strict
  --allow-flat-layouts
  --allow-dirs=agents,reference
  --skip-orphans
)

cd "$target_root"
skills_path="$target_root/$skills_dir"
if [[ ! -d "$skills_path" ]]; then
  echo "skills directory not found: $skills_path" >&2
  exit 1
fi

report=$(mktemp)
trap 'rm -f "$report"' EXIT

set +e
skill-validator "${args[@]}" --emit-annotations "$skills_path"
annotate_status=$?
skill-validator "${args[@]}" -o json "$skills_path" >"$report"
json_status=$?
set -e

if [[ "$annotate_status" -gt 2 || "$json_status" -gt 2 ]]; then
  echo "skill-validator failed to run (annotations=$annotate_status json=$json_status)" >&2
  exit 1
fi

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## Skill lint"
    echo
    echo "Strict \`skill-validator check\` of \`$skills_dir\` with skill-validator v1.8.0. A finding outside the allowlist fails the job."
    echo
  } >>"$GITHUB_STEP_SUMMARY"
  set +e
  skill-validator "${args[@]}" -o markdown "$skills_path" >>"$GITHUB_STEP_SUMMARY"
  summary_status=$?
  set -e
  if [[ "$summary_status" -gt 2 ]]; then
    echo "skill-validator markdown report failed ($summary_status)" >&2
    exit 1
  fi
fi

gate=("$script_root/scripts/skills_lint_gate.py" "$report")
if [[ "$use_allowlist" -eq 1 ]]; then
  gate+=(--allowlist "$allowlist")
fi
python3 "${gate[@]}"
