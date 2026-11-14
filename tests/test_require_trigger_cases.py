import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import require_trigger_cases as triggers


def write_skill(root, name, case=None):
    skill = root / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: %s\ndescription: Use when testing.\n---\n" % name)
    if case is not None:
        case_dir = root / "evals" / "cases"
        case_dir.mkdir(parents=True)
        (case_dir / f"{name}.json").write_text(json.dumps(case))


def test_skill_with_a_positive_trigger_passes(tmp_path):
    write_skill(
        tmp_path,
        "alpha",
        {"trigger": {"positive": [{"prompt": "Please run alpha"}], "negative": []}},
    )
    assert triggers.missing_trigger_cases(tmp_path) == []
    assert triggers.main(["require_trigger_cases.py", str(tmp_path)]) == 0


def test_missing_case_file_fails(tmp_path):
    write_skill(tmp_path, "alpha")
    problems = triggers.missing_trigger_cases(tmp_path)
    assert len(problems) == 1
    assert "no eval case file" in problems[0]
    assert triggers.main(["require_trigger_cases.py", str(tmp_path)]) == 1


def test_case_without_a_positive_prompt_fails(tmp_path, capsys):
    write_skill(
        tmp_path,
        "alpha",
        {"trigger": {"positive": [{"path": "src/a.ts"}], "negative": [{"prompt": "no"}]}},
    )
    assert triggers.main(["require_trigger_cases.py", str(tmp_path)]) == 1
    assert "0 positive trigger" in capsys.readouterr().out


def test_directory_without_skill_md_is_ignored(tmp_path):
    (tmp_path / "skills" / "notes").mkdir(parents=True)
    write_skill(
        tmp_path,
        "alpha",
        {"trigger": {"positive": [{"prompt": "Run alpha"}]}},
    )
    assert triggers.missing_trigger_cases(tmp_path) == []


def test_skills_dir_limits_which_folders_are_required(tmp_path):
    write_skill(tmp_path, "alpha")
    other = tmp_path / "other" / "beta"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: beta\ndescription: Use when testing.\n---\n")
    case_dir = tmp_path / "evals" / "cases"
    case_dir.mkdir(parents=True)
    (case_dir / "beta.json").write_text(
        json.dumps({"trigger": {"positive": [{"prompt": "Run beta"}]}})
    )
    assert triggers.missing_trigger_cases(tmp_path, "other") == []
    assert triggers.main(["require_trigger_cases.py", str(tmp_path), "--skills-dir", "other"]) == 0


def test_shipped_skills_each_have_a_trigger():
    assert triggers.missing_trigger_cases(ROOT) == []
    assert triggers.MIN_POSITIVE_TRIGGERS == 1
