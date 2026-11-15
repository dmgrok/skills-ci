#!/usr/bin/env python3
"""Run skill lint, skills-evals, and the security checks on tests/fixtures.

The job passes only when each broken fixture fails, the output contains the
expected text, and the good fixture passes. A fixture lists the tools it
runs. Security fixtures run scripts/skill_security.py and skip lint and
evals. A non-zero exit without the expected text is a failure of this job,
and so is a zero exit that still prints that text.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EXPECTATIONS = FIXTURES / "expectations.json"

# Keep these flags aligned with scripts/skills-lint.sh.
VALIDATOR_ARGS = [
    "check",
    "--strict",
    "--allow-flat-layouts",
    "--allow-dirs=agents,reference",
    "--skip-orphans",
]

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text):
    return ANSI.sub("", text)


def evaluate(exit_code, output, must_fail, needles):
    """Return (ok, missing needles). Both the exit and the text have to match."""
    text = strip_ansi(output)
    missing = [needle for needle in needles if needle not in text]
    failed = exit_code != 0
    if must_fail:
        return failed and not missing, missing
    return (not failed) and not missing, missing


def run_command(argv, cwd):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout


def tools_for(spec):
    return spec.get("tools") or ["lint", "evals"]


def tool_commands(specs):
    needed = set()
    for spec in specs:
        needed.update(tools_for(spec))
    commands = {}
    if "lint" in needed:
        validator = shutil.which("skill-validator")
        if not validator:
            raise SystemExit("skill-validator is not on PATH")
        commands["lint"] = [validator, *VALIDATOR_ARGS]
    if "evals" in needed:
        npx = shutil.which("npx")
        if not npx:
            raise SystemExit("npx is not on PATH")
        commands["evals"] = [npx, "--yes", "skills-evals@0.2.0", "run", "--root"]
    if "security" in needed:
        commands["security"] = [sys.executable, str(ROOT / "scripts" / "skill_security.py")]
    return commands


def run_fixture(fixture_dir, commands, spec):
    results = {}
    for tool in tools_for(spec):
        results[tool] = run_command([*commands[tool], str(fixture_dir)], ROOT)
    return results


def judge_fixture(name, spec, results):
    lines = []
    ok = True
    details = []
    for tool in tools_for(spec):
        status, output = results[tool]
        must_fail = spec[f"{tool}_must_fail"]
        needles = spec.get(f"{tool}_contains", [])
        passed, missing = evaluate(status, output, must_fail, needles)
        expect = "FAIL" if must_fail else "PASS"
        actual = "FAIL" if status != 0 else "PASS"
        if passed:
            lines.append(f"{tool} {actual} exit {status}, expected text matched")
        else:
            ok = False
            if missing:
                why = "missing text: " + "; ".join(missing)
            elif must_fail:
                why = "exit 0, expected a failure"
            else:
                why = f"exit {status}, expected 0"
            lines.append(f"{tool} {actual} exit {status}, expected {expect} ({why})")
            details.append((tool, output))
    return ok, lines, details


def write_summary(rows):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("## Negative fixtures\n\n")
        handle.write("| Fixture | Result | Detail |\n")
        handle.write("| --- | --- | --- |\n")
        for name, ok, detail in rows:
            handle.write(f"| `{name}` | {'pass' if ok else 'FAIL'} | {detail} |\n")
        handle.write("\n")


def main(argv):
    del argv
    if not EXPECTATIONS.is_file():
        print(f"FAIL: missing {EXPECTATIONS}", file=sys.stderr)
        return 1
    specs = json.loads(EXPECTATIONS.read_text())
    expected_names = [item["name"] for item in specs]
    found = sorted(
        p.name for p in FIXTURES.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
    )
    if found != sorted(expected_names):
        print("FAIL: fixture directories do not match expectations.json")
        print("found: " + ", ".join(found))
        print("expected: " + ", ".join(expected_names))
        return 1

    commands = tool_commands(specs)
    rows = []
    failed = False
    for spec in specs:
        name = spec["name"]
        results = run_fixture(FIXTURES / name, commands, spec)
        ok, lines, details = judge_fixture(name, spec, results)
        detail = "; ".join(lines)
        print(f"{name}: {detail}")
        rows.append((name, ok, detail))
        if not ok:
            failed = True
            for tool, output in details:
                print(f"----- {name} {tool} output -----")
                print(strip_ansi(output).rstrip())
                print(f"----- end {name} {tool} -----")
    write_summary(rows)
    if failed:
        print("FAIL: a fixture did not match its expected lint and evals result")
        return 1
    print(f"PASS: {len(specs)} fixtures matched their expected results")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
