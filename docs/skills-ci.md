# Skill CI

Canonical skills live in `skills/`. Lint points at that directory. The eval scan starts at the repository root and records each `SKILL.md` once. This repository has no plugin manifest, so CI does not validate marketplace JSON.

## What runs

| Workflow | When | What it does |
| --- | --- | --- |
| `.github/workflows/skills-lint.yml` | every pull request, and every push to `main` | `skill-validator` v1.8.0, strict, no model |
| `.github/workflows/skills-evals.yml` | every pull request, and every push to `main` | `skills-evals` v0.2.0, structural checks and trigger routing, no model and no secrets. Also fails if a skill under `skills/` has no positive trigger prompt |
| `.github/workflows/skills-tests.yml` | every pull request, and every push to `main` | pytest for the lint gate and the HTML email checker, plus negative fixtures that must fail with a specific error |
| `.github/workflows/skills-behavioral.yml` | Mondays at 06:00 UTC, and manual dispatch | behavioural tier, and only when `ANTHROPIC_API_KEY` is set |

Workflow permissions are `permissions: contents: read`. Nothing in pull-request CI needs a secret.

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

## Negative fixtures

`tests/fixtures/` sits outside `skills/`. Five directories are broken skills, and one is valid. `.github/workflows/skills-tests.yml` runs the same strict `skill-validator` check, with the same flags as `scripts/skills-lint.sh`, and `npx --yes skills-evals@0.2.0 run` on each directory alone. The job passes only when the broken fixtures fail and the output contains the expected error text. A non-zero exit with the wrong text fails the job. The valid fixture has to pass both tools.

| Fixture | What is wrong | Text the job requires |
| --- | --- | --- |
| `missing-frontmatter` | no opening `---` | lint: `name is required` and `description is required`. evals: `Missing or malformed YAML frontmatter` |
| `missing-name` | frontmatter has no `name` | lint: `name is required`. evals: `Frontmatter missing required field: 'name'` |
| `description-too-long` | description is 1100 characters | lint: `description exceeds 1024 characters`. evals: `exceeds the 1024-char limit` |
| `broken-link` | external URL returns HTTP 404 | lint: `(HTTP 404)`. skills-evals does not fetch links, so that run must pass |
| `missing-referenced-file` | markdown link to `notes/missing.md`, which is not in the skill | lint: `broken internal link: notes/missing.md (file not found)`. skills-evals does not check local links, so that run must pass |
| `good-skill` | nothing | both tools exit 0 |

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

A passing eval run can still print warnings. `ui-design` has no "Use when" clause. `html-email-report`, `research-brief-writing`, and `bs-me-not` do say "Use when", in a folded YAML block. skills-evals 0.2.0 keeps the fold marker and drops the folded lines, so it warns there too. The skill text stays as it is.

## Opt into the weekly behavioural run

Add an `evals` array to the case file. Each item needs an integer `id`, a `prompt`, an `expected_output`, and a non-empty `expectations` list. Set `"trust_level": "provisional"` until the case has fixtures under `evals/fixtures/`. The weekly workflow runs each skill whose case file has that array. It calls Claude Code when `ANTHROPIC_API_KEY` is stored as a repository secret. Keep the value out of the repository. This showcase does not store one.

### Proposal: run the behavioural tier on an open model

Not built. Pull-request CI stays on tiers 1 and 2, and this change does not add a secret.

The weekly job can later grade the same case files with an open-weights model on a self-hosted runner, instead of calling Anthropic. GitHub-hosted runners are a poor place to load these weights. A self-hosted runner would start the server on localhost, and the job would call that address. Nothing in this proposal is committed as a credential.

Two ways to serve [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct). Its `LICENSE` file at that model repo is the Apache License 2.0 (SPDX `Apache-2.0`, OSI-approved).

- **vLLM.** On the runner: `vllm serve Qwen/Qwen2.5-7B-Instruct --port 8000`. CI calls the OpenAI-compatible API at `http://127.0.0.1:8000/v1`.
- **Ollama.** On the runner: `ollama serve`, then `ollama pull qwen2.5:7b-instruct`. CI calls `http://127.0.0.1:11434`.

skills-evals 0.2.0 behavioral adapters only launch the `claude`, `copilot`, or `cursor-agent` CLIs. None of those talks to vLLM or Ollama. Using either option means a later adapter registered with `registerAdapter`, which posts the prompt to the local server and returns the text. That adapter is not in this repository. The weekly workflow is unchanged.

## Licenses of the CI tools

Read from each project's own `LICENSE` file, or from the package metadata of the pinned version, in November 2026. OSI approval is the SPDX `isOsiApproved` flag for that identifier (`MIT`, `Apache-2.0`, and `BSD-2-Clause` are all approved). No tool in this table was replaced. None is outside that set.

| Tool | Version | License | Repository | OSI-approved |
| --- | --- | --- | --- | --- |
| skill-validator | 1.8.0 | MIT | <https://github.com/agent-ecosystem/skill-validator> | yes |
| skills-evals (CLI and GitHub Action) | 0.2.0, commit `ef618aabbbd4c03cd7ccc44916f91f320eb389ea` | MIT | <https://github.com/ahnafyy/skills-evals> | yes |
| actions/checkout | 4.4.0, commit `11d5960a326750d5838078e36cf38b85af677262` | MIT | <https://github.com/actions/checkout> | yes |
| pytest | 8.4.2 | MIT | <https://github.com/pytest-dev/pytest> | yes |
| pluggy | 1.7.0 | MIT | <https://github.com/pytest-dev/pluggy> | yes |
| iniconfig | 2.3.1 | MIT | <https://github.com/pytest-dev/iniconfig> | yes |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> | yes, both |
| Pygments | 2.21.0 | BSD-2-Clause | <https://github.com/pygments/pygments> | yes |

pytest, pluggy, iniconfig, packaging, and Pygments are the packages installed from `requirements-ci.txt` for the unit-test job. The other three are the tools the lint and eval workflows already pin. The skills-evals npm package has no runtime dependencies.

## Copy the workflows into another repo

Copy the four workflow files, `scripts/skills-lint.sh`, `scripts/skills_lint_gate.py`, `scripts/skills-lint-allowlist.json`, `scripts/require_trigger_cases.py`, `scripts/run_negative_fixtures.py`, `requirements-ci.txt`, `skills-evals.config.json`, `tests/`, and this doc. Point skills at `skills/` or change the path in `scripts/skills-lint.sh` and the workflow comments together. Regenerate the allowlist only for findings you mean to keep:

```bash
skill-validator check --strict --allow-flat-layouts --allow-dirs=agents,reference --skip-orphans -o json skills/ > /tmp/lint.json
python3 scripts/skills_lint_gate.py /tmp/lint.json --write
```

Drop a layout flag your repository does not need. Keep action SHAs and the validator checksums pinned.
