# Skill CI

Canonical skills live in `skills/`. Lint points at that directory. The eval scan starts at the repository root and records each `SKILL.md` once. This repository has no plugin manifest, so CI does not validate marketplace JSON. There are no tool-specific symlink copies of the skills.

## What runs

| Workflow | When | What it does |
| --- | --- | --- |
| `.github/workflows/skills-ci.yml` | `workflow_call` from a caller | lint, trigger routing, the trigger-case check, and three security checks. No model and no secrets. Checks out this repository's scripts at the called ref |
| `.github/workflows/skills-lint.yml` | every pull request, and every push to `main` | calls `skills-ci.yml` on this repository, with `skills/` and `scripts/skills-lint-allowlist.json` |
| `.github/workflows/skills-tests.yml` | every pull request, and every push to `main` | pytest for the lint gate and the HTML email checker, plus negative fixtures that must fail with a specific error. Not part of the reusable workflow |
| `.github/workflows/skills-behavioral.yml` | Mondays at 06:00 UTC, and manual dispatch | behavioural tier, and only when `ANTHROPIC_API_KEY` is set |
| `.github/workflows/codeql.yml` | every pull request, every push to `main`, and Mondays at 09:17 UTC | CodeQL analysis of Python. No JavaScript or TypeScript. Does not analyse shell scripts |

```
pull request, or push to main
        |
        +-- Skill lint
        |     install skill-validator v1.8.0 (checksum pinned)
        |     strict check of skills/
        |     fail unless the finding list matches scripts/skills-lint-allowlist.json
        |
        +-- Skill evals
        |     every skill under skills/ must have a positive trigger prompt
        |     skills-evals v0.2.0, tiers 1 and 2 only
        |     structure, description checks, and trigger routing
        |     compare the result with .skills-evals/baseline.json
        |
        +-- Security checks
        |     injection: hidden Unicode, override phrases, exfiltration, sensitive reads
        |     license: SPDX identifier on every skill, and bundled license files
        |     malicious files: gitleaks, dangerous commands, undeclared binaries
        |
        +-- Skill tests
              pytest for the lint gate, the security checks, and the HTML email checker
              negative fixtures must fail with the expected error text
        |
        +-- CodeQL
              Python only, build-mode none
              does not analyse shell scripts
              does not replace Semgrep or gitleaks

Mondays 06:00 UTC, or a manual run
        |
        +-- Behavioural evals
              if ANTHROPIC_API_KEY is unset, print a notice and exit 0
              if it is set, run only case files that contain an evals array
              this repository ships neither the secret nor any evals array

Mondays 09:17 UTC
        |
        +-- CodeQL
              the same Python analysis as on a pull request
```

Lint, trigger routing, and the security checks in that picture run as jobs of the reusable workflow. This repository calls it from `.github/workflows/skills-lint.yml`. CodeQL is a separate workflow. Callers of the reusable workflow do not get it.

The lint, test, and behavioural workflows set `permissions: contents: read`. The CodeQL workflow sets `security-events: write`, `contents: read`, and `actions: read`. Third-party actions are pinned to commit SHAs. Nothing in pull-request CI needs a secret.

The lint job downloads the v1.8.0 Linux release archive and checks its checksum. It runs:

```bash
skill-validator check --strict --allow-flat-layouts --allow-dirs=agents,reference --skip-orphans --emit-annotations skills/
```

and appends the same check with `-o markdown` to the job summary. `check` covers structure, external links, content metrics, and contamination. It does not score with a model.

The flags match this repository:

- `--allow-flat-layouts` keeps companion files beside `SKILL.md`, such as `html-email-report`'s checker and template, and `ui-design`'s license and provenance files.
- `--allow-dirs=agents,reference` keeps `ui-design`'s `agents/` and `reference/` directories. The spec's usual reference directory is `references/`, which `ui-design` also has.
- `--skip-orphans` ignores files the skill text does not link. `ui-design` ships `LICENSE`, `NOTICE`, `CHECKSUMS.sha256`, `MANIFEST.json`, and `MODIFICATIONS.md` on purpose.

The eval job pins `ahnafyy/skills-evals` to commit `ef618aabbbd4c03cd7ccc44916f91f320eb389ea` (annotated tag v0.2.0). `actions/checkout` is pinned to `11d5960a326750d5838078e36cf38b85af677262` (v4.4.0). The `behavioral` input is left empty, so the Action runs `skills-evals run` and stops before any model call.

`skills-evals.config.json` sets `exclude` to `tests/fixtures/**`, so the broken fixtures under `tests/fixtures/` are not part of the catalog. The eval job also runs `scripts/require_trigger_cases.py` before the Action. That script fails the job when any skill under `skills/` has fewer than one positive trigger prompt. skills-evals itself only warns about a missing case file.

The weekly job reads the repository secret `ANTHROPIC_API_KEY`. This showcase does not set that secret. When the secret is absent, the job prints a notice and exits successfully. When the secret is present, the job runs behavioural evals for every file under `evals/cases/` that has an `evals` array. It installs Claude Code 2.1.323 for that step. The cases in this repository are trigger prompts only, so with the secret set and no `evals` arrays yet, the job prints a notice and exits successfully.

## Known lint finding

A green lint job still reports one warning. It is in `scripts/skills-lint-allowlist.json` and in the job summary.

- `ui-design`: the description reads as a keyword list.

Clearing it means editing skill content. The skill text stays as it was copied. A finding that is not on the allowlist fails the job. An allowlist line that the validator stops reporting also fails the job. Delete that line in the same change that fixes the skill.

## Run the linter locally

Install `skill-validator` v1.8.0 from the GitHub release, check the archive against `skill-validator_1.8.0_checksums.txt`, and put the binary on `PATH`. Then run:

```bash
scripts/skills-lint.sh
```

The script accepts only v1.8.0.

Linux amd64, file `skill-validator_1.8.0_linux_amd64.tar.gz`:

```text
a9b4cb3436682ff8d55dd0d164376c8479d35cb58c0adc3e93170fbde8baa04f
```

Linux arm64, file `skill-validator_1.8.0_linux_arm64.tar.gz`:

```text
87dc2f61df60f6c737b29e479a541ad72ee0f9c11422cdd76e7036a7e22e9fbc
```

Release page: <https://github.com/agent-ecosystem/skill-validator/releases/tag/v1.8.0>.

## Security checks

The reusable workflow runs three more jobs on `skills-dir`. Callers get them without copying scripts. The jobs read the skill tree. They do not call a model, do not log in anywhere, and do not read a secret.

These are pattern checks. They catch the shapes below. A careful rewrite of the same behavior, or a secret gitleaks does not know, will not be caught. A clean result is not a proof that a skill is safe.

### Injection

`scripts/skill_security.py --only injection` does two things.

The Python scanner reads every text file in the skill. It flags:

- Hidden Unicode: zero-width characters, bidi controls, and the other code points listed in `scripts/skill_security.py`. Ordinary punctuation and letters are left alone. Emoji variation selectors are not in the list.
- Instruction-override phrases, including `ignore previous instructions`. The list is in the script. A shorter sentence such as "ignore the previous draft" is not on it.
- A line that sends file or environment contents to a URL, such as `curl` of `.env` or a private key.
- A read of `.env`, `~/.ssh`, `id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`, or a PEM private-key header.

Semgrep CE 1.185.0 then runs `security/semgrep/injection.yml`. Those rules are in this repository. The scan passes `--oss-only`, `--metrics=off`, and `--disable-version-check`. It does not log in, and it does not load registry rules or Semgrep Pro rules. A local run of 1.185.0 reports `engine_requested` as `OSS`.

Semgrep's built-in ignore list skips a directory named `tests`, which would hide `tests/fixtures/`. This repository's `.semgrepignore` replaces that default and does not skip the fixtures. Callers do not receive the file. A caller scan uses the caller's ignore rules, or Semgrep's default, which still scans a `skills/` directory.

`scripts/install_semgrep.sh` installs from `requirements-semgrep.txt` with `pip install --require-hashes --only-binary=:all:`. That file pins Semgrep 1.185.0 and every transitive dependency for CPython 3.14 on manylinux x86_64. Every job that runs the script first runs `actions/setup-python` at commit `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (v7.1.0) with `python-version: '3.14'`. The script uses the `python3` that step puts on `PATH`, prints that path, and refuses any other version. The Semgrep wheel hash in the lock file is `0eb6aaadad5b957af96d1300487e10af1dc8016e8ef53072effb48cd4906c02b`, checked by downloading the wheel. The installer also refuses any architecture other than x86_64, because those wheels are not in the lock file.

The `COPYRIGHT` file at tag v1.185.0 says the program may be redistributed and modified "under the terms of the GNU Lesser General Public License (LGPL) version 2.1". It does not say "or any later version", so that grant is LGPL-2.1-only. The PyPI metadata for the 1.185.0 distribution says `LGPL-2.1-or-later`. The file is <https://github.com/semgrep/semgrep/blob/v1.185.0/COPYRIGHT>. The repo `LICENSE` at the same tag is the LGPL 2.1 text.

Semgrep's own licensing page describes the registry and the AppSec platform separately from the CE engine. Registry rules maintained by Semgrep are under the Semgrep Rules License v1.0, which is not an OSI license, and the AppSec platform is proprietary. This CI does not use either.

### License

The Agent Skills spec names the frontmatter field `license`. In the spec it is optional, and the spec allows a short name or a pointer at a bundled file, including free text such as `Proprietary. LICENSE.txt has complete terms`.

This CI is stricter. Every skill must set `license` to one SPDX license identifier from the pinned list. One identifier, not an expression: `MIT OR Apache-2.0` fails. The check is case-sensitive.

The pinned list is SPDX License List 3.29.0, file `json/licenses.json` at tag `v3.29.0` of [spdx/license-list-data](https://github.com/spdx/license-list-data/blob/v3.29.0/json/licenses.json). Its sha256 is `47d1cc681abe31166b342b6cc4aab13a6ba8ea5c48794697fe3bf8b1dbaf509a`. `security/spdx-licenses.json` vendors the identifier, the name, `isOsiApproved`, and `isDeprecatedLicenseId` from that file. It does not vendor license texts. `security/SPDX-NOTICE` records the attribution, that hash, that no upstream `LICENSE` file was found, and that this data is excepted from the repository's MIT grant. It does not state a licence for the data.

A declared identifier fails when it is GPL or AGPL (the strong-copyleft families this policy flags, including the deprecated `GPL-3.0` form) or when the SPDX name says non-commercial. `LGPL-2.1-only` is a valid identifier and is not in that strong-copyleft set. `CC-BY-4.0` is a valid identifier and is not non-commercial, so it passes this policy even though it is not OSI-approved. The policy is not "OSI only". `SSPL-1.0` and `BUSL-1.1` are in the pinned list and are not currently rejected: they are not GPL or AGPL, and their SPDX names do not say non-commercial.

Bundled license files are `LICENSE`, `LICENCE`, `COPYING`, `COPYING.LESSER`, `COPYRIGHT`, `UNLICENSE`, and `NOTICE`, with an optional `.txt`, `.md`, `.rst`, or `.html` suffix. A file is a problem when its text names the GNU General Public License or the GNU Affero General Public License, or says non-commercial, or matches none of the permissive phrases the script knows (Apache-2.0, MIT, BSD, ISC, 0BSD, Unlicense). An `SPDX-License-Identifier` header in any text file is checked the same way as the frontmatter field.

ScanCode Toolkit was not used. The project's README at tag `v32.5.0` says Apache-2.0 is the overall license, CC-BY-4.0 applies to reference datasets, and third-party components include GPL 2/3 among other licenses. The PyPI metadata for 32.5.0 is `Apache-2.0 AND CC-BY-4.0 AND LicenseRef-scancode-other-permissive AND LicenseRef-scancode-other-copyleft`. The cp312 wheel is 126230519 bytes before dependencies. That is a lot of install for a check that only needs an SPDX identifier and a few phrases, and the licence expression includes GPL and a non-SPDX `LicenseRef`. The lighter check is the one above.

`bs-me-not`, `html-email-report`, `research-brief-writing`, and `unslop` set `license: MIT`. They are covered by the root [LICENSE](../LICENSE). `ui-design` already set `license: Apache-2.0` and keeps its own `LICENSE` and `NOTICE`.

### Malicious files and secrets

`scripts/skill_security.py --only malicious` runs three checks.

gitleaks 8.30.1 scans the skill directory with `gitleaks detect --no-git --redact`. It uses the default rules. The report redacts the matched value. There is no path allowlist. The CI job points gitleaks at `skills-dir` only, so `tests/fixtures/` is not part of that scan. The fixture `secret-in-script` is scanned on its own by the negative-fixture job, and that scan must report `gitleaks generic-api-key`. The value in the fixture is synthetic. It was checked with gitleaks 8.30.1. It does not use a vendor prefix such as `AKIA` or `ghp_`. An allowlist was not needed.

`scripts/install_gitleaks.sh` checks the archive against `gitleaks_8.30.1_checksums.txt` from the v8.30.1 release. Linux x64 sha256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`. Linux arm64 sha256 `e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080`. Both archives were downloaded and checked.

Semgrep runs `security/semgrep/dangerous.yml`, the same CE invocation as the injection job. The rules flag `curl` or `wget` piped to `sh` or `bash`, `eval`, `rm -rf` of `/`, `~`, `$...`, or `*`, and base64-decoded bytes that are executed. Bandit was not added. It parses Python only, so it would not see `curl | sh` in a shell script. The Semgrep rules cover both.

A file is binary when it contains a NUL byte or is not valid UTF-8. A binary has to be listed in `binaries.allow` in the skill directory, one skill-relative path per line. `#` starts a comment. A listed path that is missing, or that is not binary, also fails. None of the skills in this repository ship a binary, so none of them has that file.

A symlink is scanned only when its resolved target stays inside the skill directory. The check then reads that target through the link. A symlink to a directory inside the skill is allowed and is not followed, because the real directory is already walked. A dangling symlink, a symlink that cannot be resolved, and a symlink whose target is outside the skill fail the check. The outside target is not read.

### Skill scanners that were not adopted

Dedicated scanners were looked up and not added. A scanner is added only after its `LICENSE` file at a pinned version is an OSI license, the project is maintained, and a scan of these skills works without an API key. None of them cleared that bar.

| Project | What was verified | Why it was not adopted |
| --- | --- | --- |
| [cisco-ai-defense/skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) 2.3.2 | `LICENSE` at tag `2.3.2` is Apache-2.0. The project published that release. | The recommended scan uses an LLM API key. The dependency range includes `litellm`, and the 2.3.1 notes say `litellm` 1.107.0 was a credential-stealing release. This CI does not install that tree and does not use an API key. The scanner was not run. |
| [NVIDIA/SkillSpector](https://github.com/NVIDIA/SkillSpector) v2.13.4 | `LICENSE` at tag `v2.13.4` is Apache-2.0. The release is dated 2026-11-04. | The README at that tag says the default sends file contents to an LLM provider. `--no-llm` still sends dependency names to `api.osv.dev`. This pull-request CI does not call a model or that service. A scan was not run, so it was not shown to work here. |
| [snyk/agent-scan](https://github.com/snyk/agent-scan) | `LICENSE` on the default branch is Apache-2.0, copyright 2025 Invariant Labs AG. | No release was pinned and the scanner was not run. |
| [famclaw/honeybadger](https://github.com/famclaw/honeybadger) | The repository is small and its README says it shells out to gitleaks. | Not pinned and not run. This CI already pins gitleaks itself. |
| [skilltrust/skill-detector](https://github.com/skilltrust/skill-detector) | The README describes an early v0.x CLI. | Not pinned and not run. |

## Negative fixtures

`tests/fixtures/` sits outside `skills/`. Twelve directories are broken skills, and `good-skill` and `safe-rm` are valid. `.github/workflows/skills-tests.yml` runs the strict `skill-validator` check, with the same flags as `scripts/skills-lint.sh`, and `npx --yes skills-evals@0.2.0 run`, on the lint and evals fixtures. Security fixtures run `scripts/skill_security.py` only. `good-skill` runs lint, evals, and the security checks. The job passes only when a broken fixture fails and the output contains the expected text. A non-zero exit with the wrong text fails the job. A valid fixture has to pass.

| Fixture | What is wrong | Text the job requires |
| --- | --- | --- |
| `missing-frontmatter` | no opening `---` | lint: `name is required` and `description is required`. evals: `Missing or malformed YAML frontmatter` |
| `missing-name` | frontmatter has no `name` | lint: `name is required`. evals: `Frontmatter missing required field: 'name'` |
| `description-too-long` | description is 1100 characters | lint: `description exceeds 1024 characters`. evals: `exceeds the 1024-char limit` |
| `broken-link` | external URL returns HTTP 404 | lint: `(HTTP 404)`. skills-evals does not fetch links, so that run must pass |
| `missing-referenced-file` | markdown link to `notes/missing.md`, which is not in the skill | lint: `broken internal link: notes/missing.md (file not found)`. skills-evals does not check local links, so that run must pass |
| `good-skill` | nothing | lint, evals, and the security checks exit 0 |
| `injection-hidden-text` | U+200B and U+202E in the body | `hidden Unicode U+200B` and `hidden Unicode U+202E` |
| `injection-override` | the phrase `ignore previous instructions` | `instruction override phrase: ignore previous instructions` |
| `injection-exfil` | `curl` of `.env`, and a `~/.ssh` read | `sends file or environment contents to a URL`, `reads .env, a private key, or ~/.ssh`, and the Semgrep exfiltration message |
| `license-bad` | frontmatter `Not-A-Real-License`, a GPL phrase in `COPYING`, non-commercial `NOTICE`, unrecognized `LICENSE` | `not an SPDX license identifier`, `strong copyleft`, `non-commercial`, `unknown license` |
| `secret-in-script` | a synthetic `api_key` assignment | `gitleaks generic-api-key` |
| `dangerous-command` | `curl` or `wget` piped to `sh`, `bash`, `sudo sh`, `sudo bash`, `/bin/sh`, `/bin/bash`, or `zsh`; `eval`; `rm -rf` of `/`, `~`, `$HOME`, `${HOME}`, or `*`; base64-decoded `exec` | the four `Dangerous command:` Semgrep messages |
| `safe-rm` | `rm -rf /tmp/build` only | the security checks exit 0 |
| `undeclared-binary` | `payload.bin` contains a NUL and is not in `binaries.allow` | `undeclared binary payload.bin` |

The expected strings are in `tests/fixtures/expectations.json`. `scripts/run_negative_fixtures.py` is the check.

## Add eval cases

Add `evals/cases/<skill-name>.json`. The `artifact` field matches the file name. Give it three `trigger.positive` prompts that should route to the skill, and two `trigger.negative` prompts that belong to another skill in this repository. Set `owner` on each negative prompt to that other skill's name. The owner has to outrank this skill on that prompt. Phrase the prompt the way a person would ask. Copying the description inflates the score.

```bash
npx --yes skills-evals@0.2.0 run
```

Description overlap and a missing "Use when" clause are warnings. The job fails on errors. After an intentional description change, refresh the regression snapshot and commit it:

```bash
npx --yes skills-evals@0.2.0 run --update-baseline
```

The snapshot is `.skills-evals/baseline.json`. Grading output under `.skills-evals/results/` stays untracked.

`skills-evals.config.json` sets `minEvals` to 0. In skills-evals 0.2.0 that number is the minimum count of behavioral evals in a case file (`evals[]`), and a shortfall is a warning, not an error. Raising it would ask for behavioral cases. This repository does not add those. The hard rule for trigger coverage is `scripts/require_trigger_cases.py`: every skill under `skills/` needs at least one positive trigger prompt, and the eval job fails when one is missing. The five skills already have three positive prompts and two negative prompts each, so no case file was added for this rule.

A passing eval run can still print warnings. `ui-design` has no "Use when" clause. `html-email-report`, `research-brief-writing`, and `bs-me-not` do say "Use when", in a folded YAML block. skills-evals 0.2.0 keeps the fold marker and drops the folded lines, so it warns there too. Trigger evals pass with those four warnings. Warnings do not fail the job. Rewriting those descriptions is out of scope: the copied skill files stay as they are, and `bs-me-not` keeps that fold. The skill text stays as it is.

## Opt into the weekly behavioural run

Add an `evals` array to the case file. Each item needs an integer `id`, a `prompt`, an `expected_output`, and a non-empty `expectations` list. Set `"trust_level": "provisional"` until the case has fixtures under `evals/fixtures/`. The weekly workflow runs each skill whose case file has that array. It calls Claude Code when `ANTHROPIC_API_KEY` is stored as a repository secret. Keep the value out of the repository. This showcase does not store one.

### Proposal: run the behavioural tier on an open model

Not built. Pull-request CI stays on tiers 1 and 2, and this change does not add a secret.

The weekly job can later grade the same case files with an open-weights model on a self-hosted runner, instead of calling Anthropic. GitHub-hosted runners are a poor place to load these weights. A self-hosted runner would start the server on localhost, and the job would call that address. Nothing in this proposal is committed as a credential.

Two ways to serve [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct). Its `LICENSE` file at that model repo is the Apache License 2.0 (SPDX `Apache-2.0`, OSI-approved).

- **vLLM.** On the runner: `vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000`. CI calls the OpenAI-compatible API at `http://127.0.0.1:8000/v1`.
- **Ollama.** On the runner: `ollama serve`, then `ollama pull qwen2.5:7b-instruct`. CI calls `http://127.0.0.1:11434`.

skills-evals 0.2.0 behavioral adapters only launch the `claude`, `copilot`, or `cursor-agent` CLIs. None of those talks to vLLM or Ollama. Using either option means a later adapter registered with `registerAdapter`, which posts the prompt to the local server and returns the text. That adapter is not in this repository. The weekly workflow is unchanged.

## CodeQL

`.github/workflows/codeql.yml` runs on every pull request, every push to `main`, and every Monday at 09:17 UTC. The job checks out the repository, then runs `github/codeql-action/init` and `github/codeql-action/analyze`. Both steps are pinned to commit `33d7b85da1a04171e211befe2c739303b9a4c066`, which is the commit annotated tag v4.39.3 points at. `src/defaults.json` at that commit sets the default bundle to CodeQL CLI 2.27.4 (`codeql-bundle-v2.27.4`). Python uses `build-mode: none`, so there is no autobuild step.

The language list is `python`. A search of this repository, including `tests/fixtures/` and `skills/`, found no `.js` or `.ts` files, so `javascript-typescript` is not enabled. CodeQL does not analyse shell scripts. The pinned Action's `src/languages/builtin.json` lists `actions`, `cpp`, `csharp`, `go`, `java`, `javascript`, `python`, `ruby`, `rust`, and `swift`. Shell is not in that list. `scripts/skills-lint.sh` and `skills/html-email-report/render_preview.sh` are outside this scan.

CodeQL complements Semgrep and gitleaks. It does not replace them. Semgrep and gitleaks look at skill text for injection patterns, dangerous commands, and secrets. This workflow does not run those checks. It runs the Python queries on the Python in this repository.

The workflow does not read a repository secret. It is not part of the reusable workflow.

## Licenses of the CI tools

Read from each project's own `LICENSE` file, or from the package metadata of the pinned version, in November 2026. OSI approval is the SPDX `isOsiApproved` flag for that identifier (`MIT`, `Apache-2.0`, `BSD-2-Clause`, and `LGPL-2.1` are approved). The SPDX list row is data, not a tool, and its licence was not found in a `LICENSE` file. That row is the exception. No tool in this table was replaced. The CodeQL CLI is not an OSI-approved license. The CodeQL Action and the CodeQL libraries and queries are MIT, which is OSI-approved. The wording under the table is what those files say.

| Tool | Version | License | Repository | OSI-approved |
| --- | --- | --- | --- | --- |
| skill-validator | 1.8.0 | MIT | <https://github.com/agent-ecosystem/skill-validator> | yes |
| skills-evals (CLI and GitHub Action) | 0.2.0, commit `ef618aabbbd4c03cd7ccc44916f91f320eb389ea` | MIT | <https://github.com/ahnafyy/skills-evals> | yes |
| actions/checkout | 4.4.0, commit `11d5960a326750d5838078e36cf38b85af677262` | MIT | <https://github.com/actions/checkout> | yes |
| actions/setup-python | 7.1.0, commit `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` | MIT | <https://github.com/actions/setup-python/blob/v7.1.0/LICENSE> | yes |
| github/codeql-action | v4.39.3, commit `33d7b85da1a04171e211befe2c739303b9a4c066` | MIT. The `LICENSE` file begins "MIT License" and "Permission is hereby granted, free of charge" | <https://github.com/github/codeql-action/blob/33d7b85da1a04171e211befe2c739303b9a4c066/LICENSE> | yes |
| CodeQL libraries and queries | `LICENSE` at commit `2e2b72797673638eaf94772632721d2fa5c42219` of `github/codeql` | MIT. The file begins "MIT License" and "Permission is hereby granted, free of charge". Copyright (c) 2006-2025 GitHub, Inc. | <https://github.com/github/codeql/blob/2e2b72797673638eaf94772632721d2fa5c42219/LICENSE> | yes |
| CodeQL CLI | 2.27.4, the default bundle of the pinned Action. `LICENSE.md` at tag `v2.27.4`, commit `3899e53b0d39b9dfac529c0061332fa39c2de686` | GitHub CodeQL Terms and Conditions. Not an OSI-approved license | <https://github.com/github/codeql-cli-binaries/blob/v2.27.4/LICENSE.md> | no |
| pytest | 8.4.2 | MIT | <https://github.com/pytest-dev/pytest> | yes |
| pluggy | 1.7.0 | MIT | <https://github.com/pytest-dev/pluggy> | yes |
| iniconfig | 2.3.1 | MIT | <https://github.com/pytest-dev/iniconfig> | yes |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> | yes, both |
| Pygments | 2.21.0 | BSD-2-Clause | <https://github.com/pygments/pygments> | yes |
| Semgrep CE | 1.185.0 | `COPYRIGHT` at v1.185.0 grants LGPL version 2.1 and does not say "or later" (LGPL-2.1-only). PyPI metadata says `LGPL-2.1-or-later`. The `LICENSE` file is the LGPL 2.1 text | <https://github.com/semgrep/semgrep/blob/v1.185.0/COPYRIGHT> | yes, both identifiers |
| gitleaks | 8.30.1 | MIT | <https://github.com/gitleaks/gitleaks/blob/v8.30.1/LICENSE> | yes |
| SPDX License List (identifiers only) | 3.29.0 | no `LICENSE` file at tag `v3.29.0` of `spdx/license-list-data` or `spdx/license-list-XML`. The 2018 footer on the spdx.org licences page says "All Rights Reserved." That footer is not a licence for this data. A 2012 SPDX Legal Team note puts SPDX document metadata under CC0-1.0; that note is not a `LICENSE` file in the list repository. See `security/SPDX-NOTICE` | <https://github.com/spdx/license-list-data/tree/v3.29.0> | not verified |

pytest, pluggy, iniconfig, packaging, and Pygments are the packages installed from `requirements-ci.txt` for the unit-test job. Semgrep CE and its transitive dependencies are installed from `requirements-semgrep.txt` with `pip --require-hashes`. gitleaks is the other security-check tool. The SPDX row is the identifier list used by the license check. Semgrep Pro, the Semgrep registry, and the AppSec platform are not installed. Registry rules maintained by Semgrep are under the Semgrep Rules License v1.0, which is not an OSI license, and the AppSec platform is proprietary. skill-validator, skills-evals, actions/checkout, and actions/setup-python are the other pinned tools. The skills-evals npm package has no runtime dependencies. The three CodeQL rows are the Action, the query repository, and the CLI the Action downloads.

### What the CodeQL licence files say

The Action `LICENSE` at commit `33d7b85da1a04171e211befe2c739303b9a4c066` is the MIT License, copyright (c) 2020 GitHub. It says: "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction". <https://github.com/github/codeql-action/blob/33d7b85da1a04171e211befe2c739303b9a4c066/LICENSE>

The query repository `LICENSE` at commit `2e2b72797673638eaf94772632721d2fa5c42219` is the MIT License, copyright (c) 2006-2025 GitHub, Inc. It uses the same grant sentence. The README at that commit says: "The code in this repository is licensed under the MIT License by GitHub." It then says: "The CodeQL CLI (including the CodeQL engine) is hosted in a different repository and is licensed separately. If you'd like to use the CodeQL CLI to analyze closed-source code, you will need a separate commercial license". <https://github.com/github/codeql/blob/2e2b72797673638eaf94772632721d2fa5c42219/LICENSE> and <https://github.com/github/codeql/blob/2e2b72797673638eaf94772632721d2fa5c42219/README.md>

The CLI file is `LICENSE.md` at tag `v2.27.4` (commit `3899e53b0d39b9dfac529c0061332fa39c2de686`). The title is "GitHub CodeQL Terms and Conditions". It says these Terms "are a legal agreement between you (either as an individual or on behalf of an entity) and GitHub, Inc. regarding your use of the GitHub CodeQL software and associated documentation". It defines "OSI-approved License" as "an Open Source Initiative (OSI)-approved open source software license" and "Open Source Codebase" as "a codebase that is released under an OSI-approved License." It says you may use the Software to perform academic research, to demonstrate the Software, and to test CodeQL queries that are released under an OSI-approved License. It says that, only with an Open Source Codebase, you may perform analysis on that codebase, and, if the Open Source Codebase is hosted and maintained on GitHub.com, generate CodeQL databases for or during automated analysis, CI, or CD. It says the Terms do not authorize generating a CodeQL database for automated analysis, CI, or CD in any other context, and do not authorize use "in connection with any codebase that is not an Open Source Codebase (e.g., code in a private repo in GitHub)." It says those two restrictions do not apply "if your use of the Software is under a paid customer license for GitHub Advanced Security". It says: "The Software is licensed, not sold. GitHub reserves all rights not expressly granted in these Terms." <https://github.com/github/codeql-cli-binaries/blob/v2.27.4/LICENSE.md>

The CLI repository README at that same commit has a shorter License section. It says: "By downloading, you agree to the GitHub CodeQL Terms & Conditions." That link is <https://securitylab.github.com/tools/codeql/license/>, which redirects to <https://github.com/github/codeql-cli-binaries/blob/main/LICENSE.md>. On 15 November 2026 the default branch is commit `3899e53b0d39b9dfac529c0061332fa39c2de686`, the same commit as tag v2.27.4. The README then says GitHub CodeQL "can only be used on codebases that are released under an OSI-approved open source license, or to perform academic research" and that "It can't be used to generate CodeQL databases for or during automated analysis, continuous integration or continuous delivery". `LICENSE.md` also allows generating those databases during automated analysis, CI, or CD when the codebase is an Open Source Codebase hosted and maintained on GitHub.com. <https://github.com/github/codeql-cli-binaries/blob/v2.27.4/README.md>

## Reusable workflow

Callers add one workflow file. It uses `.github/workflows/skills-ci.yml` with `on: workflow_call`. The called jobs check out the caller, then check out this repository at `job.workflow_sha` into `.skills-ci` and run the scripts from there. Callers do not copy scripts.

Inputs:

- `skills-dir`, default `skills`. A directory of skill folders, relative to the caller root.
- `allowlist`, default empty. A JSON allowlist relative to the caller root. Empty means any skill-validator finding fails. This repository passes `scripts/skills-lint-allowlist.json` because `ui-design` has one accepted warning.

The called jobs are Lint, Trigger routing, Injection, Licenses, and Malicious files. Permissions stay `contents: read`. Actions, the skill-validator archive, the Semgrep wheel, and the gitleaks archive stay pinned. The jobs do not read a secret and do not call a model. Negative fixtures and pytest stay in `.github/workflows/skills-tests.yml` and are not part of the reusable workflow.

If `evals/cases/` is missing, the trigger-case check prints a notice and continues. If that directory exists, every skill under `skills-dir` needs at least one positive trigger prompt.

This repository calls the workflow from `.github/workflows/skills-lint.yml` with a relative `uses:` path, so a pull request runs the workflow from that pull request.

## Manual setup

Use this when you cannot call a workflow in another repository. The normal path is the one-file caller in the README.

Copy `scripts/skills-lint.sh`, `scripts/skills_lint_gate.py`, `scripts/skills-lint-allowlist.json`, `scripts/require_trigger_cases.py`, `scripts/run_negative_fixtures.py`, `scripts/skill_security.py`, `scripts/install_semgrep.sh`, `scripts/install_gitleaks.sh`, `security/`, `.semgrepignore`, `requirements-ci.txt`, `requirements-semgrep.txt`, `skills-evals.config.json`, `tests/`, and this doc. Point skills at `skills/` or change the path in `scripts/skills-lint.sh` and the workflow comments together.

The same steps, in order:

1. Copy `.github/workflows/skills-behavioral.yml` if you want the weekly job, and write a workflow that runs the commands below. `.github/workflows/skills-tests.yml` is the fixture and pytest job for this repository; copy it only if you want those tests.
2. Copy `scripts/skills-lint.sh`, `scripts/skills_lint_gate.py`, `scripts/skills-lint-allowlist.json`, `scripts/require_trigger_cases.py`, `scripts/run_negative_fixtures.py`, `scripts/skill_security.py`, `scripts/install_semgrep.sh`, `scripts/install_gitleaks.sh`, `security/`, `.semgrepignore`, `requirements-ci.txt`, `requirements-semgrep.txt`, `skills-evals.config.json`, `tests/`, and `docs/skills-ci.md`.
3. Put each skill at `skills/<name>/SKILL.md`. Keep the workflow permission at `contents: read`.
4. Keep the pinned action SHAs and the skill-validator checksums. Do not switch them to a floating tag or `latest`.
5. Add `evals/cases/<name>.json` with three prompts that should route to the skill and two that should route to another skill in the same repo. See [Add eval cases](#add-eval-cases) for the shape.
6. Run the linter, `python3 scripts/skill_security.py skills`, and `npx --yes skills-evals@0.2.0 run --update-baseline`. Commit `.skills-evals/baseline.json`.
7. Leave `ANTHROPIC_API_KEY` unset unless you intentionally want the weekly behavioural job to call a model. Do not commit the key.

If your skills use a different layout, change the flags in `scripts/skills-lint.sh` and say why in your own doc. This repo allows companion files beside `SKILL.md`, allows `agents/` and `reference/` (used by `ui-design`), and skips orphan checks so license and provenance files are not treated as forgotten references.

Regenerate the allowlist only for findings you mean to keep:

```bash
skill-validator check --strict --allow-flat-layouts --allow-dirs=agents,reference --skip-orphans -o json skills/ > /tmp/lint.json
python3 scripts/skills_lint_gate.py /tmp/lint.json --write
```

Drop a layout flag your repository does not need. Keep action SHAs and the validator checksums pinned.
