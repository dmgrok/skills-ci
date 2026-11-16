import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import skillspector_gate as gate


def test_scan_command_is_static_sarif_without_a_severity_flag():
    command = gate.scan_command("skillspector", Path("skills/demo"), Path("out.sarif"), None)
    assert command[:3] == ["skillspector", "scan", "skills/demo"]
    assert "--no-llm" in command
    assert "--format" in command and "sarif" in command
    assert "--baseline" not in command
    assert "--fail-on-findings" not in command
    assert "--recursive" not in command

    with_baseline = gate.scan_command(
        "skillspector", Path("skills/demo"), Path("out.sarif"), Path("base.yaml")
    )
    assert with_baseline[with_baseline.index("--baseline") + 1] == "base.yaml"


def test_scanner_env_drops_provider_credentials():
    env = gate.scanner_env(
        {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant",
            "CUSTOM_API_TOKEN": "secret",
            "LANGSMITH_API_KEY": "ls",
            "GITHUB_TOKEN": "ghs_test",
            "HOME": "/tmp/home",
        }
    )
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/tmp/home"
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "CUSTOM_API_TOKEN" not in env
    assert "LANGSMITH_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert env["LANGCHAIN_TRACING_V2"] == "false"
    assert env["LANGSMITH_TRACING"] == "false"


def test_blocking_uses_sarif_severity_and_ignores_baseline_hits():
    high = {"properties": {"severity": "HIGH"}, "ruleId": "P1"}
    medium = {"properties": {"severity": "medium"}, "ruleId": "E1"}
    low = {"properties": {"severity": "LOW"}, "ruleId": "EA3"}
    suppressed = {
        "properties": {"severity": "CRITICAL"},
        "ruleId": "TM1",
        "suppressions": [{"kind": "external"}],
    }
    missing = {"ruleId": "X", "level": "error"}
    assert gate.is_blocking(high)
    assert not gate.is_blocking(medium)
    assert not gate.is_blocking(low)
    assert not gate.is_blocking(suppressed)
    assert not gate.is_blocking(missing)
    assert gate.result_severity(medium) == "MEDIUM"


def test_normalize_uri_prefixes_the_skill_directory():
    workspace = Path("/repo")
    assert gate.normalize_uri("SKILL.md", "skills/demo", workspace) == "skills/demo/SKILL.md"
    assert (
        gate.normalize_uri("skills/demo/SKILL.md", "skills/demo", workspace)
        == "skills/demo/SKILL.md"
    )
    assert gate.normalize_uri("https://example.invalid/a", "skills/demo", workspace).startswith(
        "https://"
    )


def test_merge_sarif_rewrites_locations_and_keeps_rules():
    workspace = Path("/repo")
    first = {
        "version": "2.1.0",
        "$schema": "https://example.invalid/sarif.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "skillspector",
                        "version": "2.13.4",
                        "rules": [{"id": "P1", "shortDescription": {"text": "Override"}}],
                    }
                },
                "results": [
                    {
                        "ruleId": "P1",
                        "level": "error",
                        "message": {"text": "Instruction Override"},
                        "properties": {"severity": "HIGH"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "SKILL.md"},
                                    "region": {"startLine": 4},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }
    merged = gate.merge_sarif([("tests/fixtures/injection-override", first)], workspace)
    result = merged["runs"][0]["results"][0]
    uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "tests/fixtures/injection-override/SKILL.md"
    assert merged["runs"][0]["tool"]["driver"]["rules"][0]["id"] == "P1"
    record = gate.record_from_result(result, "injection-override", "tests/fixtures/injection-override")
    assert record["blocking"]
    assert record["location"] == "tests/fixtures/injection-override/SKILL.md:4"
    assert gate.format_counts(gate.count_results([record], blocking_only=True)) == "HIGH P1 x1"


def test_resolve_inside_rejects_a_path_that_leaves_the_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    inside = workspace / "skills"
    inside.mkdir()
    assert gate.resolve_inside(workspace, "skills") == inside.resolve()
    try:
        gate.resolve_inside(workspace, "../outside")
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("expected a path outside the workspace to fail")


def test_workflows_pin_the_scanner_and_keep_caller_permissions():
    reusable = (ROOT / ".github/workflows/skills-ci.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    install = (ROOT / "scripts/install_skillspector.sh").read_text(encoding="utf-8")
    gate_text = (ROOT / "scripts/skillspector_gate.py").read_text(encoding="utf-8")
    reusable_code = "\n".join(
        line for line in reusable.splitlines() if not line.strip().startswith("#")
    )
    assert "skillspector-baseline:" in reusable
    assert "required: false" in reusable
    assert "security-events" not in reusable_code
    assert "install_skillspector.sh" in reusable
    assert "54824463814a0be01360792523ec7245a69190fc" in install
    assert '"--no-llm"' in gate_text
    assert '"--fail-on-findings"' not in gate_text
    assert '"--recursive"' not in gate_text
    assert "github/codeql-action/upload-sarif@33d7b85da1a04171e211befe2c739303b9a4c066" in codeql
    assert "category: skillspector" in codeql
    assert "security-events: write" in codeql
