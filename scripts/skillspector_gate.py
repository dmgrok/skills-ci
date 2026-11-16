#!/usr/bin/env python3
"""Run SkillSpector with --no-llm and fail on active HIGH or CRITICAL findings.

SkillSpector 2.13.4 has no severity-threshold flag. --fail-on-findings exits 1
when any active finding remains, including LOW and MEDIUM. The default exit
code is 1 when the risk score is above 50. One HIGH finding scores 25 and
does not, by itself, produce that exit. This script reads the SARIF report
and fails when an active result has properties.severity HIGH or CRITICAL.
Results with a suppressions array were accepted by --baseline and do not
fail the gate.

Each directory that contains SKILL.md is scanned on its own. v2.13.4 rejects
--baseline together with --recursive, so a caller baseline is passed to every
single-skill scan instead.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import skill_security

BLOCKING = ("HIGH", "CRITICAL")
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
PINNED_VERSION = "2.13.4"
SCAN_TIMEOUT_SECONDS = 180

# Credential variables named by SkillSpector 2.13.4, plus the tracing keys
# that would send a run to LangSmith. --no-llm already skips the LLM client.
# Removing these keeps a leaked runner secret out of the scanner process.
SECRET_ENV = {
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_PROXY_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_API_KEY",
    "NODE_AUTH_TOKEN",
    "NPM_TOKEN",
    "NVIDIA_INFERENCE_KEY",
    "OPENAI_API_KEY",
    "SKILLSPECTOR_COMPAT_API_KEY",
}
SECRET_SUFFIXES = ("_API_KEY", "_API_TOKEN", "_TOKEN", "_SECRET", "_PASSWORD")


def scanner_env(base):
    """Return an environment for the scanner with provider credentials removed."""
    env = dict(base)
    for key in list(env):
        upper = key.upper()
        if upper in SECRET_ENV or upper.endswith(SECRET_SUFFIXES):
            env.pop(key, None)
    env["LANGCHAIN_TRACING_V2"] = "false"
    env["LANGSMITH_TRACING"] = "false"
    env["SKILLSPECTOR_LOG_LEVEL"] = "WARNING"
    return env


def scan_command(binary, skill, output, baseline):
    """Build the only scan invocation this CI uses."""
    command = [
        binary,
        "scan",
        str(skill),
        "--no-llm",
        "--format",
        "sarif",
        "--output",
        str(output),
    ]
    if baseline is not None:
        command.extend(["--baseline", str(baseline)])
    return command


def resolve_inside(workspace, raw):
    """Resolve raw against workspace and reject a path that leaves it."""
    workspace = workspace.resolve()
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    try:
        path.relative_to(workspace)
    except ValueError:
        raise ValueError("path is outside the workspace: %s" % raw)
    return path


def result_severity(result):
    """Return the SkillSpector severity string, or empty when it is absent."""
    props = result.get("properties") or {}
    severity = props.get("severity")
    if isinstance(severity, str) and severity.strip():
        return severity.strip().upper()
    return ""


def is_suppressed(result):
    return bool(result.get("suppressions"))


def is_blocking(result):
    """An active HIGH or CRITICAL result fails the job."""
    if is_suppressed(result):
        return False
    return result_severity(result) in BLOCKING


def normalize_uri(uri, skill_prefix, workspace):
    """Make a SARIF artifact URI relative to the workspace."""
    if not isinstance(uri, str) or not uri:
        return uri
    raw = uri.replace("\\", "/")
    if "://" in raw:
        return raw
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(workspace.resolve()).as_posix()
        except ValueError:
            return raw
    prefix = skill_prefix.strip("/")
    if not prefix or raw == prefix or raw.startswith(prefix + "/"):
        return raw
    return prefix + "/" + raw.lstrip("/")


def _rewrite_location(location, skill_prefix, workspace):
    if not isinstance(location, dict):
        return
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return
    artifact = physical.get("artifactLocation")
    if isinstance(artifact, dict) and "uri" in artifact:
        artifact["uri"] = normalize_uri(artifact.get("uri"), skill_prefix, workspace)


def rewrite_result(result, skill_prefix, workspace):
    """Return a copy of one SARIF result with workspace-relative paths."""
    copied = json.loads(json.dumps(result))
    for location in copied.get("locations") or []:
        _rewrite_location(location, skill_prefix, workspace)
    for location in copied.get("relatedLocations") or []:
        _rewrite_location(location, skill_prefix, workspace)
    return copied


def merge_sarif(parts, workspace):
    """Combine per-skill SARIF documents into one report.

    parts is a list of (skill_prefix, document) pairs. Rules are keyed by id.
    """
    version = "2.1.0"
    schema = None
    tool = None
    rules = {}
    results = []
    for skill_prefix, document in parts:
        if not isinstance(document, dict):
            continue
        version = document.get("version") or version
        schema = document.get("$schema") or schema
        for run in document.get("runs") or []:
            if tool is None and isinstance(run.get("tool"), dict):
                tool = json.loads(json.dumps(run["tool"]))
            driver = (run.get("tool") or {}).get("driver") or {}
            for rule in driver.get("rules") or []:
                rule_id = rule.get("id")
                if rule_id and rule_id not in rules:
                    rules[rule_id] = json.loads(json.dumps(rule))
            for result in run.get("results") or []:
                results.append(rewrite_result(result, skill_prefix, workspace))
    if tool is None:
        tool = {"driver": {"name": "skillspector", "version": PINNED_VERSION, "rules": []}}
    driver = tool.setdefault("driver", {})
    driver["rules"] = [rules[key] for key in sorted(rules)]
    document = {"version": version, "runs": [{"tool": tool, "results": results}]}
    if schema:
        document["$schema"] = schema
    return document


def result_location(result):
    """Return the first file:line for a result, or an empty string."""
    for location in result.get("locations") or []:
        physical = (location or {}).get("physicalLocation") or {}
        artifact = (physical.get("artifactLocation") or {}).get("uri") or ""
        region = physical.get("region") or {}
        line = region.get("startLine")
        if artifact and line:
            return "%s:%s" % (artifact, line)
        if artifact:
            return str(artifact)
    return ""


def record_from_result(result, skill_name, skill_prefix):
    return {
        "skill": skill_name,
        "skill_path": skill_prefix,
        "rule": result.get("ruleId") or "",
        "severity": result_severity(result),
        "level": result.get("level") or "",
        "location": result_location(result),
        "suppressed": is_suppressed(result),
        "message": ((result.get("message") or {}).get("text") or ""),
        "blocking": is_blocking(result),
    }


def format_counts(counter):
    """Render (severity, rule) counts as 'HIGH SC2 x7, MEDIUM E1 x1'."""
    items = sorted(
        counter.items(),
        key=lambda item: (SEVERITY_ORDER.get(item[0][0], 9), item[0][1]),
    )
    return ", ".join("%s %s x%d" % (severity, rule, count) for (severity, rule), count in items)


def count_results(records, blocking_only=False):
    """Count active results. Suppressed baseline hits are left out."""
    counter = Counter()
    for record in records:
        if record["suppressed"]:
            continue
        if blocking_only and not record["blocking"]:
            continue
        counter[(record["severity"] or "UNKNOWN", record["rule"] or "UNKNOWN")] += 1
    return counter


def skill_dirs(root):
    return skill_security.iter_skills(root)


def _which(binary):
    from shutil import which

    return which(binary)


def _run(command, env):
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=env,
        timeout=SCAN_TIMEOUT_SECONDS,
    )


def run_gate(skills_dir, workspace, sarif_path, baseline=None, binary=None):
    """Scan skills_dir. Write sarif_path. Return a result dict with code 0, 1, or 2."""
    workspace = Path(workspace).resolve()
    skills_root = resolve_inside(workspace, skills_dir)
    if not skills_root.is_dir():
        print("FAIL: skills directory not found: %s" % skills_root)
        return {"code": 2, "records": [], "skills": []}
    skills = skill_dirs(skills_root)
    if not skills:
        print("FAIL: no SKILL.md found under %s" % skills_root)
        return {"code": 2, "records": [], "skills": []}

    baseline_path = None
    if baseline:
        baseline_path = resolve_inside(workspace, baseline)
        if not baseline_path.is_file():
            print("FAIL: baseline file not found: %s" % baseline_path)
            return {"code": 2, "records": [], "skills": []}

    binary = binary or _which("skillspector")
    if not binary:
        print("FAIL: skillspector is not on PATH")
        return {"code": 2, "records": [], "skills": []}

    env = scanner_env(os.environ)
    version = _run([binary, "--version"], env)
    print(version.stdout.strip())
    if version.returncode != 0 or ("v%s" % PINNED_VERSION) not in version.stdout:
        print("FAIL: expected SkillSpector v%s" % PINNED_VERSION)
        return {"code": 2, "records": [], "skills": []}

    parts = []
    records = []
    skill_rows = []
    sarif_dir = Path(sarif_path).resolve().parent
    sarif_dir.mkdir(parents=True, exist_ok=True)
    for index, skill in enumerate(skills):
        prefix = skill.resolve().relative_to(workspace).as_posix()
        partial = sarif_dir / ("skillspector-%d.sarif" % index)
        command = scan_command(binary, skill, partial, baseline_path)
        print("+ " + " ".join(command))
        try:
            proc = _run(command, env)
        except subprocess.TimeoutExpired:
            print("FAIL: skillspector timed out after %ss on %s" % (SCAN_TIMEOUT_SECONDS, prefix))
            return {"code": 2, "records": records, "skills": skill_rows}
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.returncode not in (0, 1) or not partial.is_file():
            print("FAIL: skillspector exit %s on %s" % (proc.returncode, prefix))
            return {"code": 2, "records": records, "skills": skill_rows}
        try:
            document = json.loads(partial.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print("FAIL: SARIF from %s was not JSON: %s" % (prefix, exc))
            return {"code": 2, "records": records, "skills": skill_rows}
        parts.append((prefix, document))
        skill_records = []
        for run in document.get("runs") or []:
            for result in run.get("results") or []:
                rewritten = rewrite_result(result, prefix, workspace)
                skill_records.append(record_from_result(rewritten, skill.name, prefix))
        records.extend(skill_records)
        full = count_results(skill_records)
        blocking = count_results(skill_records, blocking_only=True)
        row = {
            "name": skill.name,
            "path": prefix,
            "cli_exit": proc.returncode,
            "active": format_counts(full) or "none",
            "blocking": format_counts(blocking) or "none",
        }
        skill_rows.append(row)
        print(
            "skill %s cli_exit=%s active=%s blocking=%s"
            % (prefix, row["cli_exit"], row["active"], row["blocking"])
        )
        partial.unlink(missing_ok=True)

    document = merge_sarif(parts, workspace)
    Path(sarif_path).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print("wrote SARIF %s" % sarif_path)
    blocking_records = [record for record in records if record["blocking"]]
    _write_summary(skill_rows, bool(blocking_records))
    if blocking_records:
        print("FAIL: active HIGH or CRITICAL SkillSpector findings")
        return {"code": 1, "records": records, "skills": skill_rows}
    print("PASS: no active HIGH or CRITICAL SkillSpector findings")
    return {"code": 0, "records": records, "skills": skill_rows}


def _write_summary(skill_rows, failed):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("## SkillSpector\n\n")
        handle.write("Gate: active SARIF `properties.severity` of HIGH or CRITICAL.\n\n")
        handle.write("| Skill | CLI exit | Active findings | Blocking |\n")
        handle.write("| --- | --- | --- | --- |\n")
        for row in skill_rows:
            handle.write(
                "| `%s` | %s | %s | %s |\n"
                % (row["path"], row["cli_exit"], row["active"], row["blocking"])
            )
        handle.write("\n")
        if failed:
            handle.write("The job fails because an active finding is HIGH or CRITICAL.\n\n")
        else:
            handle.write("No active HIGH or CRITICAL finding.\n\n")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="SkillSpector --no-llm gate")
    parser.add_argument("--skills-dir", required=True)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--sarif", required=True)
    parser.add_argument("--baseline", default="")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    baseline = args.baseline or os.environ.get("SKILLSPECTOR_BASELINE", "")
    try:
        result = run_gate(
            skills_dir=args.skills_dir,
            workspace=args.workspace,
            sarif_path=args.sarif,
            baseline=baseline or None,
        )
    except ValueError as exc:
        print("FAIL: %s" % exc)
        return 2
    return result["code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
