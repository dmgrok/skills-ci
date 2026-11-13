# Skill CI

Canonical skills live in `skills/`. Lint points at that directory. The eval scan starts at the repository root and records each `SKILL.md` once. This repository has no plugin manifest, so CI does not validate marketplace JSON.

## What runs

| Workflow | When | What it does |
| --- | --- | --- |
| `.github/workflows/skills-lint.yml` | every pull request, and every push to `main` | `skill-validator` v1.8.0, strict, no model |
| `.github/workflows/skills-evals.yml` | every pull request, and every push to `main` | `skills-evals` v0.2.0, structural checks and trigger routing, no model and no secrets |
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

`skills-evals.config.json` sets `minEvals` to 0 so a case file made of trigger prompts is complete for pull-request CI.

A passing eval run can still print warnings. `ui-design` has no "Use when" clause. `html-email-report` and `research-brief-writing` do say "Use when", in a folded YAML block. skills-evals 0.2.0 keeps the fold marker and drops the folded lines, so it warns there too. The skill text stays as it is.

## Opt into the weekly behavioural run

Add an `evals` array to the case file. Each item needs an integer `id`, a `prompt`, an `expected_output`, and a non-empty `expectations` list. Set `"trust_level": "provisional"` until the case has fixtures under `evals/fixtures/`. The weekly workflow runs each skill whose case file has that array. It calls Claude Code when `ANTHROPIC_API_KEY` is stored as a repository secret. Keep the value out of the repository. This showcase does not store one.

## Copy the workflows into another repo

Copy the three workflow files, `scripts/skills-lint.sh`, `scripts/skills_lint_gate.py`, `scripts/skills-lint-allowlist.json`, `skills-evals.config.json`, and this doc. Point skills at `skills/` or change the path in `scripts/skills-lint.sh` and the workflow comments together. Regenerate the allowlist only for findings you mean to keep:

```bash
skill-validator check --strict --allow-flat-layouts --allow-dirs=agents,reference --skip-orphans -o json skills/ > /tmp/lint.json
python3 scripts/skills_lint_gate.py /tmp/lint.json --write
```

Drop a layout flag your repository does not need. Keep action SHAs and the validator checksums pinned.
