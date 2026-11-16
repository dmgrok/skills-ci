#!/usr/bin/env python3
"""Compare SkillSpector with the existing security checks on tests/fixtures.

The process exits 0 when the scan tools finish, good-skill has no active
HIGH or CRITICAL finding, and skills/ has none either. A malicious fixture
that SkillSpector flags does not fail this process. The reusable-workflow
gate is what fails the job for those findings. This report records both.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import skill_security
import skillspector_gate as gate

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EXPECTATIONS = FIXTURES / "expectations.json"
SECURITY = ROOT / "scripts" / "skill_security.py"

INJECTION = {
    "hidden-unicode",
    "instruction-override",
    "exfiltration",
    "sensitive-read",
    "semgrep-curl-env-upload",
    "semgrep-requests-env-upload",
    "semgrep-sensitive-path-read",
}
MALICIOUS_SEMGREP = {
    "semgrep-curl-pipe-shell",
    "semgrep-shell-eval",
    "semgrep-rm-rf-root",
    "semgrep-base64-decode-exec",
}


def bucket(code):
    if code in INJECTION:
        return "injection"
    if code == "license" or code.startswith("license-"):
        return "licenses"
    if (
        code.startswith("gitleaks")
        or code == "binary"
        or code.startswith("binary-")
        or code in MALICIOUS_SEMGREP
        or code == "symlink"
    ):
        return "malicious files"
    return "other"


def current_checks(fixture_dir):
    """Return (exit_code, label). label is 'none' when every check passes."""
    proc = subprocess.run(
        [sys.executable, str(SECURITY), "--only", "all", str(fixture_dir)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode == 0:
        return 0, "none"
    grouped = {}
    for line in proc.stdout.splitlines():
        if not line.startswith("FAIL "):
            continue
        rest = line[len("FAIL ") :]
        code = rest.split(":", 1)[0].strip()
        grouped.setdefault(bucket(code), []).append(code)
    if not grouped:
        return proc.returncode, "exit %s" % proc.returncode
    parts = []
    for name in ("injection", "licenses", "malicious files", "other"):
        codes = grouped.get(name)
        if not codes:
            continue
        # Keep the first sighting of each code, in order.
        seen = []
        for code in codes:
            if code not in seen:
                seen.append(code)
        parts.append("%s (%s)" % (name, ", ".join(seen)))
    return proc.returncode, "; ".join(parts)


def records_for(records, skill_path):
    return [record for record in records if record["skill_path"] == skill_path]


def skillspector_cell(records):
    active = [record for record in records if not record["suppressed"]]
    if not active:
        return "no"
    blocking = gate.format_counts(gate.count_results(active, blocking_only=True))
    other = gate.format_counts(
        gate.count_results([record for record in active if not record["blocking"]])
    )
    if blocking and other:
        return "yes (%s; also %s)" % (blocking, other)
    if blocking:
        return "yes (%s)" % blocking
    return "no (%s)" % other


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [cell.replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
        handle.write("\n")


def load_expectations():
    specs = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))
    malicious = []
    clean = []
    other = []
    for spec in specs:
        name = spec["name"]
        tools = spec.get("tools") or []
        if "security" in tools and spec.get("security_must_fail"):
            malicious.append(name)
        elif "security" in tools and spec.get("security_must_fail") is False:
            clean.append(name)
        else:
            other.append(name)
    return malicious, clean, other


def require_current_tools():
    """The comparison is only meaningful when the existing scanners run."""
    missing = []
    for binary, expected in (
        ("semgrep", skill_security.SEMGREP_VERSION),
        ("gitleaks", skill_security.GITLEAKS_VERSION),
    ):
        problem = skill_security.require_tool(binary, expected)
        if problem:
            missing.append(problem["detail"])
    return missing


def main(argv):
    del argv
    missing = require_current_tools()
    if missing:
        for detail in missing:
            print("FAIL: %s" % detail)
        return 2
    workspace = ROOT
    fixture_sarif = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "skillspector-fixtures.sarif"
    skills_sarif = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "skillspector-skills.sarif"
    try:
        fixture_result = gate.run_gate(
            skills_dir=FIXTURES,
            workspace=workspace,
            sarif_path=fixture_sarif,
        )
        skills_result = gate.run_gate(
            skills_dir=ROOT / "skills",
            workspace=workspace,
            sarif_path=skills_sarif,
        )
    except ValueError as exc:
        print("FAIL: %s" % exc)
        return 2
    if fixture_result["code"] == 2 or skills_result["code"] == 2:
        print("FAIL: SkillSpector did not finish")
        return 2

    malicious, clean, other = load_expectations()
    by_path = {}
    for record in fixture_result["records"]:
        by_path.setdefault(record["skill_path"], []).append(record)

    def row_for(name):
        path = "tests/fixtures/%s" % name
        spec_records = by_path.get(path, [])
        _code, checks = current_checks(FIXTURES / name)
        return [name, skillspector_cell(spec_records), checks]

    malicious_rows = [row_for(name) for name in malicious]
    clean_rows = [row_for(name) for name in clean]
    other_rows = []
    for name in other:
        path = "tests/fixtures/%s" % name
        spec_records = by_path.get(path, [])
        active = [record for record in spec_records if not record["suppressed"]]
        if not active:
            continue
        _code, checks = current_checks(FIXTURES / name)
        other_rows.append([name, skillspector_cell(spec_records), checks])

    both = []
    spector_only = []
    checks_only = []
    neither = []
    for name, spector, checks in malicious_rows:
        spector_hit = spector.startswith("yes")
        checks_hit = checks != "none"
        if spector_hit and checks_hit:
            both.append(name)
        elif spector_hit:
            spector_only.append(name)
        elif checks_hit:
            checks_only.append(name)
        else:
            neither.append(name)

    shipped_rows = []
    for row in skills_result["skills"]:
        shipped_rows.append([row["path"], "cli_exit=%s" % row["cli_exit"], row["active"], row["blocking"]])

    sections = []
    sections.append("## SkillSpector fixture comparison\n")
    sections.append("SkillSpector caught means an active HIGH or CRITICAL result.\n")
    sections.append("### Malicious fixtures\n")
    sections.append(
        markdown_table(
            ["Fixture", "SkillSpector caught?", "Current checks caught?"],
            [["`%s`" % name, spector, checks] for name, spector, checks in malicious_rows],
        )
    )
    sections.append("\n### Overlap\n")
    sections.append("- Both: %s" % (", ".join(both) or "none"))
    sections.append("- SkillSpector only: %s" % (", ".join(spector_only) or "none"))
    sections.append("- Current checks only: %s" % (", ".join(checks_only) or "none"))
    sections.append("- Neither: %s" % (", ".join(neither) or "none"))
    sections.append("\n### Clean security fixtures\n")
    sections.append(
        markdown_table(
            ["Fixture", "SkillSpector caught?", "Current checks caught?"],
            [["`%s`" % name, spector, checks] for name, spector, checks in clean_rows],
        )
    )
    if other_rows:
        sections.append("\n### Other fixtures with SkillSpector results\n")
        sections.append(
            markdown_table(
                ["Fixture", "SkillSpector caught?", "Current checks caught?"],
                [["`%s`" % name, spector, checks] for name, spector, checks in other_rows],
            )
        )
    sections.append("\n### Shipped skills\n")
    sections.append(
        markdown_table(
            ["Skill", "CLI exit", "Active findings", "Blocking"],
            shipped_rows,
        )
    )
    text = "\n".join(sections) + "\n"
    print(text)
    write_summary(text)

    failed = False
    good = by_path.get("tests/fixtures/good-skill", [])
    if any(record["blocking"] for record in good):
        print("FAIL: good-skill has an active HIGH or CRITICAL finding")
        failed = True
    if skills_result["code"] == 1:
        print("FAIL: skills/ has an active HIGH or CRITICAL finding")
        failed = True
    if failed:
        return 1
    print("PASS: good-skill and skills/ have no active HIGH or CRITICAL finding")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
