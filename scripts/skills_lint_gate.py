#!/usr/bin/env python3
"""Fail skill lint when findings differ from the committed allowlist.

skill-validator v1.8.0 may report findings in skills this repository
ships unchanged. Those are recorded in scripts/skills-lint-allowlist.json
because clearing them would mean rewriting skill content. This gate fails
the job when a finding appears that is not on that list, and when a listed
finding disappears, so the list cannot drift.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "skills-lint-allowlist.json"


def signature(skill, result):
    message = re.sub(r"\d+", "#", result.get("message", ""))
    message = " ".join(message.split())
    return {
        "skill": skill,
        "level": result.get("level", ""),
        "category": result.get("category", ""),
        "file": result.get("file") or "",
        "message": message,
    }


def finding_key(item):
    return (
        item["skill"],
        item["level"],
        item["category"],
        item["file"],
        item["message"],
    )


def iter_findings(report):
    skills = report.get("skills")
    if skills is None:
        skills = [report]
    for skill in skills:
        raw_dir = skill.get("skill_dir", "").rstrip("/")
        name = raw_dir.split("/")[-1] if raw_dir else skill.get("name", "")
        for result in skill.get("results", []):
            if result.get("level") in ("error", "warning"):
                yield signature(name, result)


def load_report(path):
    report = json.loads(Path(path).read_text())
    findings = list(iter_findings(report))
    return sorted(findings, key=finding_key)


def load_allowlist(path):
    data = json.loads(path.read_text())
    findings = data.get("findings", data)
    return sorted(findings, key=finding_key)


def write_allowlist(findings, path):
    payload = {
        "validator": "skill-validator v1.8.0",
        "note": (
            "Known findings from a strict check of skills/. "
            "Remove an entry only after the validator stops reporting it. "
            "A new finding fails CI until it is fixed or added here on purpose."
        ),
        "findings": findings,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def format_finding(item):
    location = item["file"] or "(skill)"
    return (
        f"{item['skill']}: {item['level']} [{item['category']}] "
        f"{location}: {item['message']}"
    )


def main(argv):
    if len(argv) < 2:
        print("usage: skills_lint_gate.py <report.json> [--write]", file=sys.stderr)
        return 2
    report_path = argv[1]
    write = "--write" in argv[2:]
    current = load_report(report_path)
    if write:
        write_allowlist(current, ALLOWLIST)
        print(f"wrote {len(current)} findings to {ALLOWLIST.relative_to(ROOT)}")
        return 0
    if not ALLOWLIST.is_file():
        print(f"FAIL: missing allowlist {ALLOWLIST}", file=sys.stderr)
        return 1
    expected = load_allowlist(ALLOWLIST)
    current_keys = {finding_key(item) for item in current}
    expected_keys = {finding_key(item) for item in expected}
    new = [item for item in current if finding_key(item) not in expected_keys]
    stale = [item for item in expected if finding_key(item) not in current_keys]
    if not new and not stale:
        print(f"PASS: {len(current)} known skill-validator findings, none new")
        return 0
    for item in new:
        print("FAIL: new finding: " + format_finding(item))
    for item in stale:
        print("FAIL: allowlist entry no longer reported: " + format_finding(item))
    print("Update scripts/skills-lint-allowlist.json only when the change is intentional.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
