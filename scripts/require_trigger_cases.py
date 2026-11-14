#!/usr/bin/env python3
"""Fail unless every skill under skills/ has a positive trigger prompt.

skills-evals 0.2.0 treats a missing case file as a warning. Its minEvals
setting counts entries in the behavioral evals array, and a shortfall is
also only a warning. This repository does not run behavioral evals, so
minEvals stays 0. This script is what makes a skill with no trigger case
fail the job.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_POSITIVE_TRIGGERS = 1


def positive_prompts(data):
    prompts = []
    for item in data.get("trigger", {}).get("positive") or []:
        if isinstance(item, dict) and str(item.get("prompt", "")).strip():
            prompts.append(item["prompt"].strip())
    return prompts


def missing_trigger_cases(root):
    skills_dir = root / "skills"
    problems = []
    if not skills_dir.is_dir():
        return [f"missing skills directory: {skills_dir}"]
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        case_path = root / "evals" / "cases" / f"{skill_dir.name}.json"
        if not case_path.is_file():
            problems.append(f"{skill_dir.name}: no eval case file at {case_path.relative_to(root)}")
            continue
        try:
            data = json.loads(case_path.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"{skill_dir.name}: invalid JSON in {case_path.name}: {exc}")
            continue
        found = positive_prompts(data)
        if len(found) < MIN_POSITIVE_TRIGGERS:
            problems.append(
                f"{skill_dir.name}: {len(found)} positive trigger prompt(s); "
                f"need at least {MIN_POSITIVE_TRIGGERS}"
            )
    return problems


def main(argv):
    root = Path(argv[1]).resolve() if len(argv) > 1 else ROOT
    problems = missing_trigger_cases(root)
    if problems:
        print(f"FAIL: every skill needs at least {MIN_POSITIVE_TRIGGERS} positive trigger prompt")
        for problem in problems:
            print("FAIL: " + problem)
        return 1
    skills = [
        p.name
        for p in sorted((root / "skills").iterdir())
        if p.is_dir() and (p / "SKILL.md").is_file()
    ]
    print(
        f"PASS: {len(skills)} skill(s), each with at least "
        f"{MIN_POSITIVE_TRIGGERS} positive trigger prompt"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
