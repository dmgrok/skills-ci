#!/usr/bin/env bash
# Strict skill-validator check used by .github/workflows/skills-lint.yml.
# Requires skill-validator v1.8.0 on PATH. See docs/skills-ci.md.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

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

report=$(mktemp)
trap 'rm -f "$report"' EXIT

set +e
skill-validator "${args[@]}" --emit-annotations skills/
annotate_status=$?
skill-validator "${args[@]}" -o json skills/ >"$report"
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
    echo "Strict \`skill-validator check\` of \`skills/\` with skill-validator v1.8.0. The summary lists every finding. \`scripts/skills-lint-allowlist.json\` records findings already accepted for the skills in this repository. A finding outside that file fails the job."
    echo
  } >>"$GITHUB_STEP_SUMMARY"
  set +e
  skill-validator "${args[@]}" -o markdown skills/ >>"$GITHUB_STEP_SUMMARY"
  summary_status=$?
  set -e
  if [[ "$summary_status" -gt 2 ]]; then
    echo "skill-validator markdown report failed ($summary_status)" >&2
    exit 1
  fi
fi

python3 scripts/skills_lint_gate.py "$report"
