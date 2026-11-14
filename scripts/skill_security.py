#!/usr/bin/env python3
"""Security checks for a directory of Agent Skills.

Three checks, selected with --only:

- injection: hidden Unicode, instruction-override phrases, exfiltration,
  and reads of .env, a private key, or ~/.ssh. Semgrep CE runs the rules
  in security/semgrep/injection.yml.
- license: the SKILL.md frontmatter license field, plus bundled license
  files. The field is the one the Agent Skills spec names `license`.
- malicious: gitleaks, Semgrep rules in security/semgrep/dangerous.yml,
  and binary files that are not listed in binaries.allow.

Pattern checks catch the shapes listed in docs/skills-ci.md. They do not
catch a well-disguised rewrite of the same behavior.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPDX_LIST = ROOT / "security" / "spdx-licenses.json"
INJECTION_RULES = ROOT / "security" / "semgrep" / "injection.yml"
DANGEROUS_RULES = ROOT / "security" / "semgrep" / "dangerous.yml"

SEMGREP_VERSION = "1.185.0"
GITLEAKS_VERSION = "8.30.1"

CHECKS = ("injection", "license", "malicious")

# Characters that hide or reorder text. Variation selectors and emoji
# joiners used as part of an emoji are not in this set. This repository's
# skills do not use U+200D, so a zero-width joiner is still flagged.
HIDDEN = {
    "\u00ad": "SOFT HYPHEN",
    "\u034f": "COMBINING GRAPHEME JOINER",
    "\u115f": "HANGUL CHOSEONG FILLER",
    "\u1160": "HANGUL JUNGSEONG FILLER",
    "\u17b4": "KHMER VOWEL INHERENT AQ",
    "\u17b5": "KHMER VOWEL INHERENT AA",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\u202a": "LEFT-TO-RIGHT EMBEDDING",
    "\u202b": "RIGHT-TO-LEFT EMBEDDING",
    "\u202c": "POP DIRECTIONAL FORMATTING",
    "\u202d": "LEFT-TO-RIGHT OVERRIDE",
    "\u202e": "RIGHT-TO-LEFT OVERRIDE",
    "\u2060": "WORD JOINER",
    "\u2066": "LEFT-TO-RIGHT ISOLATE",
    "\u2067": "RIGHT-TO-LEFT ISOLATE",
    "\u2068": "FIRST STRONG ISOLATE",
    "\u2069": "POP DIRECTIONAL ISOLATE",
    "\u3164": "HANGUL FILLER",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE",
    "\uffa0": "HALFWIDTH HANGUL FILLER",
}

OVERRIDE_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore prior instructions",
    "disregard previous instructions",
    "disregard your instructions",
    "disregard the above instructions",
    "forget your previous instructions",
    "forget all previous instructions",
    "do not follow the previous instructions",
    "override the system prompt",
)

EXFIL_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:curl|wget)\b[^\n]{0,300}(?:\.env\b|~/?.ssh\b|\bid_rsa\b|\bid_ed25519\b|\bprintenv\b|\$\(env\))"
    r"|(?:\.env\b|~/?.ssh\b|\bid_rsa\b|\bid_ed25519\b)[^\n]{0,300}\b(?:curl|wget|https?://)"
    r"|\brequests\.(?:post|put)\s*\([^\n]{0,300}(?:environ|\.env\b|\bid_rsa\b|~/?.ssh\b)"
    r")"
)

SENSITIVE_RE = re.compile(
    r"(?i)(?:"
    r"~/?.ssh\b"
    r"|\bid_rsa\b|\bid_ed25519\b|\bid_ecdsa\b|\bid_dsa\b"
    r"|BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY"
    r"|(?:^|[^\w.])\.env\b"
    r")"
)

LICENSE_FILENAMES = {
    "license",
    "licence",
    "copying",
    "copying.lesser",
    "copyright",
    "unlicense",
    "notice",
}
LICENSE_EXTENSIONS = {".txt", ".md", ".rst", ".html", ""}

COPYLEFT_RE = re.compile(
    r"GNU General Public License|GNU Affero General Public License|\bAGPL\b|\bGPL-[123]",
    re.IGNORECASE,
)
NONCOMMERCIAL_RE = re.compile(
    r"non-?commercial|not for commercial use|no commercial use",
    re.IGNORECASE,
)
PERMISSIVE_RES = (
    re.compile(r"Apache License,?\s+Version 2\.0", re.IGNORECASE),
    re.compile(r"\bMIT License\b|Permission is hereby granted, free of charge", re.IGNORECASE),
    re.compile(r"Redistribution and use in source and binary forms", re.IGNORECASE),
    re.compile(r"\bISC License\b|Permission to use, copy, modify, and/or distribute this software", re.IGNORECASE),
    re.compile(r"BSD Zero Clause|Zero-Clause BSD", re.IGNORECASE),
    re.compile(r"This is free and unencumbered software released into the public domain", re.IGNORECASE),
)
SPDX_HEADER_RE = re.compile(r"(?m)^[^\n]*SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)\s*$")


def hidden_name(char):
    if char in HIDDEN:
        return HIDDEN[char]
    code = ord(char)
    if code == 0xE0001 or 0xE0020 <= code <= 0xE007F:
        return "TAG CHARACTER"
    return None


def load_spdx():
    data = json.loads(SPDX_LIST.read_text())
    by_id = {item["licenseId"]: item for item in data["licenses"]}
    return data, by_id


def licence_problem(entry):
    """Return a problem label, or None.

    GPL and AGPL are the strong-copyleft families this policy flags.
    LGPL is not in that set. Non-commercial is decided from the SPDX name.
    """
    ident = entry["licenseId"]
    if ident.startswith("GPL-") or ident.startswith("AGPL-"):
        return "strong copyleft"
    name = entry["name"].lower()
    if "non-commercial" in name or "noncommercial" in name or "non commercial" in name:
        return "non-commercial"
    return None


def split_frontmatter(text):
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    return None


def license_field(frontmatter):
    if frontmatter is None:
        return None
    for line in frontmatter.splitlines():
        if line.startswith("license:"):
            value = line.split(":", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].strip()
            return value
    return None


def is_license_filename(path):
    name = path.name.lower()
    stem = name
    suffix = ""
    if "." in name:
        stem, suffix = name.rsplit(".", 1)
        suffix = "." + suffix
    if stem in LICENSE_FILENAMES and suffix in LICENSE_EXTENSIONS:
        return True
    return name in LICENSE_FILENAMES


def classify_license_text(text):
    problems = []
    if COPYLEFT_RE.search(text):
        problems.append("strong copyleft")
    if NONCOMMERCIAL_RE.search(text):
        problems.append("non-commercial")
    if problems:
        return problems
    if any(pattern.search(text) for pattern in PERMISSIVE_RES):
        return []
    return ["unknown license"]


def read_bytes(path):
    return path.read_bytes()


def is_binary_bytes(data):
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def iter_files(skill_dir):
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def relative(path, root):
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def finding(code, location, detail):
    return {"code": code, "location": location, "detail": detail}


def format_finding(item):
    return "FAIL %s: %s: %s" % (item["code"], item["location"], item["detail"])


def text_findings_in_file(path, location):
    data = read_bytes(path)
    if is_binary_bytes(data):
        return []
    text = data.decode("utf-8")
    found = []
    seen_chars = set()
    seen_phrases = set()
    exfil = False
    sensitive = False
    for lineno, line in enumerate(text.splitlines(), 1):
        for char in line:
            name = hidden_name(char)
            if name and char not in seen_chars:
                seen_chars.add(char)
                found.append(
                    finding(
                        "hidden-unicode",
                        "%s:%d" % (location, lineno),
                        "hidden Unicode U+%04X %s" % (ord(char), name),
                    )
                )
        lowered = line.lower()
        for phrase in OVERRIDE_PHRASES:
            if phrase in lowered and phrase not in seen_phrases:
                seen_phrases.add(phrase)
                found.append(
                    finding(
                        "instruction-override",
                        "%s:%d" % (location, lineno),
                        "instruction override phrase: %s" % phrase,
                    )
                )
        if not exfil and EXFIL_RE.search(line):
            exfil = True
            found.append(
                finding(
                    "exfiltration",
                    "%s:%d" % (location, lineno),
                    "sends file or environment contents to a URL",
                )
            )
        if not sensitive and SENSITIVE_RE.search(line):
            sensitive = True
            found.append(
                finding(
                    "sensitive-read",
                    "%s:%d" % (location, lineno),
                    "reads .env, a private key, or ~/.ssh",
                )
            )
    return found


def text_findings(skill_dir):
    found = []
    for path in iter_files(skill_dir):
        location = "%s/%s" % (skill_dir.name, relative(path, skill_dir))
        found.extend(text_findings_in_file(path, location))
    return found


def license_findings(skill_dir, spdx_by_id=None):
    if spdx_by_id is None:
        _meta, spdx_by_id = load_spdx()
    found = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [finding("license", skill_dir.name, "missing SKILL.md")]
    text = skill_md.read_text(encoding="utf-8")
    value = license_field(split_frontmatter(text))
    location = "%s/SKILL.md" % skill_dir.name
    if value is None or value == "":
        found.append(finding("license", location, "missing license field"))
    elif value not in spdx_by_id:
        found.append(
            finding(
                "license",
                location,
                "not an SPDX license identifier: %s" % value,
            )
        )
    else:
        problem = licence_problem(spdx_by_id[value])
        if problem:
            found.append(
                finding(
                    "license",
                    location,
                    "license %s is %s" % (value, problem),
                )
            )
    for path in iter_files(skill_dir):
        rel = relative(path, skill_dir)
        loc = "%s/%s" % (skill_dir.name, rel)
        data = read_bytes(path)
        if is_binary_bytes(data):
            continue
        file_text = data.decode("utf-8")
        if is_license_filename(path):
            for problem in classify_license_text(file_text):
                found.append(
                    finding("license", loc, "bundled %s: %s" % (path.name, problem))
                )
        for match in SPDX_HEADER_RE.finditer(file_text):
            ident = match.group(1)
            if ident not in spdx_by_id:
                found.append(
                    finding(
                        "license",
                        loc,
                        "SPDX-License-Identifier is not an SPDX license identifier: %s" % ident,
                    )
                )
                continue
            problem = licence_problem(spdx_by_id[ident])
            if problem:
                found.append(
                    finding(
                        "license",
                        loc,
                        "SPDX-License-Identifier %s is %s" % (ident, problem),
                    )
                )
    return found


def parse_binary_allowlist(skill_dir):
    path = skill_dir / "binaries.allow"
    if not path.is_file():
        return [], []
    declared = []
    errors = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return [], [finding("binary", "%s/binaries.allow" % skill_dir.name, "binaries.allow is not UTF-8 text")]
    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = Path(line).parts
        if line.startswith("/") or ".." in parts or "\\" in line:
            errors.append(
                finding(
                    "binary",
                    "%s/binaries.allow:%d" % (skill_dir.name, lineno),
                    "binary allowlist path must stay inside the skill: %s" % line,
                )
            )
            continue
        declared.append(line)
    return declared, errors


def binary_findings(skill_dir):
    declared, errors = parse_binary_allowlist(skill_dir)
    found = list(errors)
    binaries = set()
    for path in iter_files(skill_dir):
        rel = relative(path, skill_dir)
        if rel == "binaries.allow":
            continue
        if is_binary_bytes(read_bytes(path)):
            binaries.add(rel)
            if rel not in declared:
                found.append(
                    finding(
                        "binary",
                        "%s/%s" % (skill_dir.name, rel),
                        "undeclared binary %s" % rel,
                    )
                )
    for rel in declared:
        target = skill_dir / rel
        if not target.is_file() or target.is_symlink():
            found.append(
                finding(
                    "binary",
                    "%s/binaries.allow" % skill_dir.name,
                    "declared binary is missing: %s" % rel,
                )
            )
        elif rel not in binaries:
            found.append(
                finding(
                    "binary",
                    "%s/%s" % (skill_dir.name, rel),
                    "declared path is not a binary file: %s" % rel,
                )
            )
    return found


def iter_skills(root):
    root = Path(root)
    if not root.is_dir():
        return []
    if (root / "SKILL.md").is_file():
        return [root]
    return [
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "SKILL.md").is_file()
    ]


def command_version(argv):
    proc = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env=tool_env(),
    )
    return proc.returncode, proc.stdout.strip()


def tool_env():
    env = os.environ.copy()
    env["SEMGREP_SEND_METRICS"] = "off"
    env["SEMGREP_ENABLE_VERSION_CHECK"] = "false"
    return env


def require_tool(binary, expected):
    from shutil import which

    path = which(binary)
    if not path:
        return finding(binary, ".", "%s is not on PATH" % binary)
    status, output = command_version([path, "--version"])
    if status != 0 or expected not in output:
        return finding(
            binary,
            ".",
            "expected %s %s, found: %s" % (binary, expected, output or "exit %s" % status),
        )
    return None


def semgrep_findings(root, rules_path):
    problem = require_tool("semgrep", SEMGREP_VERSION)
    if problem:
        return [problem]
    proc = subprocess.run(
        [
            "semgrep",
            "scan",
            "--metrics=off",
            "--disable-version-check",
            "--oss-only",
            "--no-git-ignore",
            "--json",
            "--config",
            str(rules_path),
            str(root),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=tool_env(),
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr or proc.stdout or "no output").strip()
        return [finding("semgrep", ".", "semgrep did not return JSON: %s" % detail[:500])]
    found = []
    for error in report.get("errors") or []:
        message = error.get("message") if isinstance(error, dict) else str(error)
        found.append(finding("semgrep", ".", "semgrep error: %s" % message))
    engine = report.get("engine_requested")
    if engine and engine != "OSS":
        found.append(finding("semgrep", ".", "expected the OSS engine, found: %s" % engine))
    for result in report.get("results") or []:
        check_id = result.get("check_id", "semgrep")
        rule_id = check_id.split(".")[-1]
        path = Path(result.get("path", ""))
        line = result.get("start", {}).get("line", 1)
        location = "%s:%s" % (relative(path, root), line)
        message = result.get("extra", {}).get("message", rule_id)
        found.append(finding("semgrep-%s" % rule_id, location, message))
    if proc.returncode not in (0, 1) and not found:
        found.append(finding("semgrep", ".", "semgrep exited %s" % proc.returncode))
    return found


def gitleaks_findings(root):
    problem = require_tool("gitleaks", GITLEAKS_VERSION)
    if problem:
        return [problem]
    report_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    report_path = report_dir / ("gitleaks-%s.json" % os.getpid())
    proc = subprocess.run(
        [
            "gitleaks",
            "detect",
            "--no-git",
            "--no-banner",
            "--redact",
            "--source",
            str(root),
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if not report_path.is_file():
        return [finding("gitleaks", ".", "gitleaks exited %s without a report" % proc.returncode)]
    try:
        leaks = json.loads(report_path.read_text())
    except json.JSONDecodeError as exc:
        return [finding("gitleaks", ".", "gitleaks report was not JSON: %s" % exc)]
    finally:
        report_path.unlink(missing_ok=True)
    found = []
    for leak in leaks:
        rule_id = leak.get("RuleID", "secret")
        path = Path(leak.get("File", ""))
        location = relative(path, root)
        found.append(
            finding(
                "gitleaks-%s" % rule_id,
                location,
                "gitleaks %s" % rule_id,
            )
        )
    if proc.returncode not in (0, 1) and not found:
        found.append(finding("gitleaks", ".", "gitleaks exited %s" % proc.returncode))
    return found


def collect(root, only="all"):
    root = Path(root)
    skills = iter_skills(root)
    if not skills:
        return [finding("security", str(root), "no SKILL.md found")]
    selected = CHECKS if only == "all" else (only,)
    found = []
    if "injection" in selected:
        for skill in skills:
            found.extend(text_findings(skill))
        found.extend(semgrep_findings(root, INJECTION_RULES))
    if "license" in selected:
        _meta, spdx_by_id = load_spdx()
        for skill in skills:
            found.extend(license_findings(skill, spdx_by_id))
    if "malicious" in selected:
        for skill in skills:
            found.extend(binary_findings(skill))
        found.extend(gitleaks_findings(root))
        found.extend(semgrep_findings(root, DANGEROUS_RULES))
    return sorted(found, key=lambda item: (item["location"], item["code"], item["detail"]))


def pass_line(only):
    if only == "all":
        return "PASS: security checks passed"
    return "PASS: %s checks passed" % only


def write_summary(only, found):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    title = "Security checks" if only == "all" else "Security checks (%s)" % only
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("## %s\n\n" % title)
        if not found:
            handle.write("%s\n\n" % pass_line(only))
            return
        handle.write("| Check | Location | Detail |\n")
        handle.write("| --- | --- | --- |\n")
        for item in found:
            detail = item["detail"].replace("|", "\\|")
            handle.write("| `%s` | `%s` | %s |\n" % (item["code"], item["location"], detail))
        handle.write("\n")


def parse_args(argv):
    only = "all"
    paths = []
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--only":
            if index + 1 >= len(argv):
                return None
            only = argv[index + 1]
            index += 2
        else:
            paths.append(arg)
            index += 1
    if only not in CHECKS and only != "all":
        return None
    if len(paths) != 1:
        return None
    return only, Path(paths[0])


def main(argv):
    parsed = parse_args(argv)
    if parsed is None:
        print(
            "usage: skill_security.py [--only injection|license|malicious|all] <skills-dir>",
            file=sys.stderr,
        )
        return 2
    only, root = parsed
    if not root.is_dir():
        print("FAIL security: %s: skills directory not found" % root)
        return 1
    found = collect(root, only)
    if not found:
        print(pass_line(only))
        write_summary(only, found)
        return 0
    for item in found:
        print(format_finding(item))
    write_summary(only, found)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
