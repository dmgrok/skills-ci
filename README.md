# skills-ci

CI for [Agent Skills](https://agentskills.io) that proves it catches a broken skill.

[![Skill CI](https://github.com/dmgrok/skills-ci/actions/workflows/skills-lint.yml/badge.svg?branch=main)](https://github.com/dmgrok/skills-ci/actions/workflows/skills-lint.yml)
[![Skill tests](https://github.com/dmgrok/skills-ci/actions/workflows/skills-tests.yml/badge.svg?branch=main)](https://github.com/dmgrok/skills-ci/actions/workflows/skills-tests.yml)
[![License: MIT, ui-design Apache-2.0](https://img.shields.io/badge/license-MIT_(root),_Apache--2.0_(ui--design)-blue)](LICENSE)

A CI run that only ever goes green proves nothing. This repository ships deliberately broken skills. Each one must fail with its expected error text, and one valid skill must pass.

## What it catches

| Problem | Caught by lint | Caught by evals |
| --- | --- | --- |
| Missing frontmatter (`missing-frontmatter`) | yes | yes |
| Missing name (`missing-name`) | yes | yes |
| Description longer than 1024 characters (`description-too-long`) | yes | yes |
| External link returns HTTP 404 (`broken-link`) | yes | no |
| Link to a file that is not in the skill (`missing-referenced-file`) | yes | no |
| Valid skill (`good-skill`) | passes | passes |

The fixtures are under `tests/fixtures/`, outside `skills/`. Expected strings are in `tests/fixtures/expectations.json`.

## Security checks

The reusable workflow also runs three pattern checks on `skills/`. They catch known shapes. They do not catch a well-disguised rewrite, and a clean result is not a proof that a skill is safe.

| Check | What a failure looks like |
| --- | --- |
| Injection | Hidden Unicode, an instruction-override phrase, exfiltration to a URL, or a read of `.env`, a private key, or `~/.ssh` |
| License | A missing or invalid SPDX `license` field, or a bundled GPL, AGPL, non-commercial, or unknown license |
| Malicious files | A gitleaks secret, `curl` piped to a shell, `eval`, `rm -rf` of a root path, base64-decoded execution, or a binary that is not listed in `binaries.allow` |

The fixtures and the limits are in [docs/skills-ci.md](docs/skills-ci.md#security-checks).

SkillSpector 2.13.4 (commit `54824463814a0be01360792523ec7245a69190fc`, tag `v2.13.4`) scans the same `skills/` tree with `--no-llm` only. File contents are not sent to an LLM provider. The job sets no API key and reads no secret. Check SC4, Known Vulnerable Dependency, still runs. When a skill path contains a dependency manifest (`requirements`, `package.json`, `package-lock.json`, `npm-shrinkwrap.json`, `pyproject.toml`, `setup.py`, `pipfile`, `uv.lock`, or `poetry.lock`), SC4 posts the package name and ecosystem (`PyPI` or `npm`), and the version when the manifest pins one, to `https://api.osv.dev/v1/querybatch`. It may then GET `https://api.osv.dev/v1/vulns/{id}`. That request does not include file contents and does not use an API key. `query_batch` returns without an HTTP call when the package list is empty, so a skill with no such manifest does not make the call. If OSV.dev cannot be reached, SkillSpector uses a small built-in fallback list. A fallback match is HIGH. A live match uses the advisory severity. A package with no pinned version is reported as LOW.

v2.13.4 has no flag that fails the job only for high or critical findings. `--fail-on-findings` fails on any active finding. The default exit code is 1 when the risk score is above 50, so one HIGH finding (25 points) does not fail the command. The workflow reads SARIF `properties.severity` and fails when an active result is HIGH or CRITICAL. Medium and low results stay in the report and the job still passes. A baseline hit is a SARIF result with `suppressions`, and it does not fail the job.

The optional input `skillspector-baseline` is a path in the caller repository. Empty, the default, suppresses nothing. The file is the one `skillspector scan --baseline` reads. In v2.13.4, `--baseline` cannot be combined with `--recursive`, so each directory that contains `SKILL.md` is scanned on its own and the same baseline is passed to every scan. Glob rules use `id`, `path`, and `message`. `skillspector baseline --no-llm` writes fingerprint entries. Upstream describes the file in `docs/SUPPRESSION.md` at tag `v2.13.4`.

The reusable workflow keeps `permissions: contents: read`. It does not request `security-events: write`, so a caller that only grants `contents: read` still runs, with no new input and no new secret. This repository uploads the SARIF from `.github/workflows/codeql.yml`, which already has `security-events: write`, using `github/codeql-action/upload-sarif` at the same commit as the CodeQL steps and the category `skillspector`. The uploaded report includes SkillSpector's `code_snippet` text, so matched excerpts are stored by GitHub code scanning.

## Use it in your repo in 3 steps

1. Put each skill at `skills/<name>/SKILL.md`.
2. Add `.github/workflows/skills-ci.yml`:

```yaml
name: Skill CI
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  skills:
    uses: dmgrok/skills-ci/.github/workflows/skills-ci.yml@main
```

3. Optional: add `evals/cases/<name>.json` with trigger prompts. Until that directory exists, the trigger-case check is skipped. Optional: pass `skillspector-baseline` when you have accepted SkillSpector false positives. Leave it unset and every active HIGH or CRITICAL finding fails the job.

`@main` follows the default branch. A tag or a commit SHA is safer. Use `@v1` after that tag exists. This repository does not publish it yet. Copying the scripts by hand is the [manual setup](docs/skills-ci.md#manual-setup).

## What runs

On every pull request, and on every push to `main`. No model, and no secrets. SkillSpector runs with `--no-llm`. Check SC4 can still send package names to OSV.dev, as described under Security checks.

- **Skill lint.** A strict check of `skills/`.
- **Skill evals.** Structure checks and trigger routing.
- **Security checks.** Injection, SPDX `license`, and malicious files, on `skills/`.
- **SkillSpector.** Static scan of `skills/` with `--no-llm`. The job fails on active HIGH or CRITICAL findings. SARIF upload for this repository is in the CodeQL workflow.
- **Skill tests.** In this repository: pytest, and the fixture check in the tables above. Callers do not run that job.
- **CodeQL.** Python on every pull request, every push to `main`, and weekly. It does not analyse shell scripts, and it does not replace Semgrep or gitleaks.

The optional behavioural tier is off by default. A proposal for running it later with an open-weights model is in [docs/skills-ci.md](docs/skills-ci.md#proposal-run-the-behavioural-tier-on-an-open-model).

## Open source

The CodeQL CLI is not an OSI-approved license. It is under the GitHub CodeQL Terms and Conditions. The CodeQL Action and the query libraries are MIT. The other tools this CI installs are under OSI-approved licenses. The table is in [docs/skills-ci.md](docs/skills-ci.md#licenses-of-the-ci-tools).

## Skills included

| Skill | What it is for |
| --- | --- |
| `bs-me-not` | Prefer truth over a confident guess on research, reviews, and factual claims |
| `html-email-report` | Turn a written brief into a Gmail-safe HTML email with a plain-text alternative |
| `research-brief-writing` | Turn sourced notes into a daily or weekly decision brief |
| `unslop` | Edit draft prose to remove model-ish patterns |
| `ui-design` | Design or improve a web or native interface. Apache-2.0 skill; see its `LICENSE` and `NOTICE` |

`bs-me-not`, `html-email-report`, `research-brief-writing`, and `unslop` are covered by the MIT [LICENSE](LICENSE) at the repository root. `ui-design` keeps its own Apache-2.0 license and third-party notices. The root MIT license does not replace that skill's license.

## Credits

- [skill-validator](https://github.com/agent-ecosystem/skill-validator) v1.8.0. MIT License, copyright 2026 Dachary Carey. The lint job downloads the Linux release archive and checks it against the checksums published with that release.
- [skills-evals](https://github.com/ahnafyy/skills-evals) v0.2.0, commit `ef618aabbbd4c03cd7ccc44916f91f320eb389ea`. MIT License, copyright 2026 Ahnaf Prio. Docs: <https://ahnafyy.github.io/skills-evals/>.
- [Semgrep CE](https://github.com/semgrep/semgrep) 1.185.0. `COPYRIGHT` at that tag grants LGPL version 2.1 and does not say "or later". PyPI metadata says `LGPL-2.1-or-later`. Our rules only. No registry and no Semgrep Pro.
- [gitleaks](https://github.com/gitleaks/gitleaks) 8.30.1. MIT License. The release archive is checksum-pinned.
- [SkillSpector](https://github.com/NVIDIA/SkillSpector) 2.13.4, commit `54824463814a0be01360792523ec7245a69190fc`. Apache-2.0. Installed from that commit with `--no-llm`.
- [Agent Skills specification](https://github.com/agentskills/agentskills) and <https://agentskills.io>. Code and the specification are Apache License 2.0. Documentation is CC-BY-4.0. See the upstream `LICENSE` and `GOVERNANCE.md`.
- `ui-design` adapts [Impeccable](https://github.com/pbakaus/impeccable) by Paul Bakaus (Apache-2.0). Its iOS notes also carry the MIT notice for [platform-design-skills](https://github.com/ehmo/platform-design-skills). Both notices are in `skills/ui-design/`.
