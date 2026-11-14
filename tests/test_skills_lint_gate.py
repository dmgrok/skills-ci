import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import skills_lint_gate as gate


def write_report(path, skills):
    path.write_text(json.dumps({"skills": skills}))


def skill(name, results, skill_dir=None):
    payload = {"name": name, "results": results}
    if skill_dir is not None:
        payload["skill_dir"] = skill_dir
    return payload


def test_signature_collapses_digits_and_whitespace():
    item = gate.signature(
        "ui-design",
        {
            "level": "warning",
            "category": "Frontmatter",
            "file": "SKILL.md",
            "message": "description has  8\ncomma-separated segments",
        },
    )
    assert item["message"] == "description has # comma-separated segments"
    assert item["skill"] == "ui-design"


def test_iter_findings_uses_directory_name_and_skips_info():
    report = {
        "skills": [
            skill(
                "ignored",
                [
                    {"level": "info", "category": "Frontmatter", "file": "SKILL.md", "message": "ok"},
                    {
                        "level": "error",
                        "category": "Frontmatter",
                        "file": None,
                        "message": "name is required",
                    },
                ],
                skill_dir="skills/unslop/",
            )
        ]
    }
    findings = list(gate.iter_findings(report))
    assert findings == [
        {
            "skill": "unslop",
            "level": "error",
            "category": "Frontmatter",
            "file": "",
            "message": "name is required",
        }
    ]


def test_single_report_without_skills_array():
    report = skill(
        "demo",
        [{"level": "warning", "category": "Links", "file": "SKILL.md", "message": "HTTP 404"}],
    )
    findings = list(gate.iter_findings(report))
    assert findings[0]["skill"] == "demo"
    assert findings[0]["message"] == "HTTP #"


def test_matching_report_passes(tmp_path, monkeypatch, capsys):
    finding = {
        "skill": "ui-design",
        "level": "warning",
        "category": "Frontmatter",
        "file": "SKILL.md",
        "message": "description has # comma-separated segments",
    }
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"findings": [finding]}))
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            skill(
                "ui-design",
                [
                    {
                        "level": "warning",
                        "category": "Frontmatter",
                        "file": "SKILL.md",
                        "message": "description has 8 comma-separated segments",
                    }
                ],
                skill_dir="skills/ui-design",
            )
        ],
    )
    monkeypatch.setattr(gate, "ALLOWLIST", allow)
    assert gate.main(["skills_lint_gate.py", str(report)]) == 0
    assert "PASS:" in capsys.readouterr().out


def test_new_finding_fails(tmp_path, monkeypatch, capsys):
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"findings": []}))
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            skill(
                "unslop",
                [
                    {
                        "level": "error",
                        "category": "Frontmatter",
                        "file": "SKILL.md",
                        "message": "name is required",
                    }
                ],
                skill_dir="skills/unslop",
            )
        ],
    )
    monkeypatch.setattr(gate, "ALLOWLIST", allow)
    assert gate.main(["skills_lint_gate.py", str(report)]) == 1
    err = capsys.readouterr().out
    assert "FAIL: new finding: unslop: error [Frontmatter] SKILL.md: name is required" in err


def test_stale_allowlist_entry_fails(tmp_path, monkeypatch, capsys):
    finding = {
        "skill": "ui-design",
        "level": "warning",
        "category": "Frontmatter",
        "file": "SKILL.md",
        "message": "old warning",
    }
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"findings": [finding]}))
    report = tmp_path / "report.json"
    write_report(report, [skill("ui-design", [], skill_dir="skills/ui-design")])
    monkeypatch.setattr(gate, "ALLOWLIST", allow)
    assert gate.main(["skills_lint_gate.py", str(report)]) == 1
    assert "allowlist entry no longer reported" in capsys.readouterr().out


def test_missing_allowlist_fails(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"
    write_report(report, [])
    monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "missing.json")
    assert gate.main(["skills_lint_gate.py", str(report)]) == 1
    assert "missing allowlist" in capsys.readouterr().err


def test_write_replaces_allowlist(tmp_path, monkeypatch, capsys):
    allow = tmp_path / "allow.json"
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            skill(
                "demo",
                [
                    {
                        "level": "error",
                        "category": "Links",
                        "file": "SKILL.md",
                        "message": "HTTP 404",
                    }
                ],
                skill_dir="skills/demo",
            )
        ],
    )
    monkeypatch.setattr(gate, "ALLOWLIST", allow)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    assert gate.main(["skills_lint_gate.py", str(report), "--write"]) == 0
    written = json.loads(allow.read_text())
    assert written["findings"][0]["message"] == "HTTP #"
    assert "wrote 1 findings" in capsys.readouterr().out


def test_allowlist_flag_overrides_the_default(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            skill(
                "demo",
                [
                    {
                        "level": "error",
                        "category": "Frontmatter",
                        "file": "SKILL.md",
                        "message": "name is required",
                    }
                ],
                skill_dir="skills/demo",
            )
        ],
    )
    empty = tmp_path / "empty.json"
    empty.write_text('{"findings": []}')
    monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "unused.json")
    assert gate.main(["skills_lint_gate.py", str(report), "--allowlist", str(empty)]) == 1
    assert "new finding" in capsys.readouterr().out


def test_usage_error(capsys):
    assert gate.main(["skills_lint_gate.py"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_committed_allowlist_is_the_ui_design_warning():
    findings = gate.load_allowlist(ROOT / "scripts" / "skills-lint-allowlist.json")
    assert [item["skill"] for item in findings] == ["ui-design"]
    assert findings[0]["level"] == "warning"
    assert "keyword list" in findings[0]["message"]
