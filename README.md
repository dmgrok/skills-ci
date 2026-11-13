# skills-ci

A small, reusable CI pipeline for [Agent Skills](https://agentskills.io): folders whose instructions live in `SKILL.md`.

Two checks run on every pull request and every push to `main`. Neither check calls a model or reads a secret. A third workflow runs weekly and does nothing unless you later add a repository secret and behavioural cases.

Skills in this repository live at `skills/<name>/`. There are no tool-specific symlink copies.

## Pipeline

```
pull request, or push to main
        |
        +-- Skill lint
        |     install skill-validator v1.8.0 (checksum pinned)
        |     strict check of skills/
        |     fail unless the finding list matches scripts/skills-lint-allowlist.json
        |
        +-- Skill evals
              skills-evals v0.2.0, tiers 1 and 2 only
              structure, description checks, and trigger routing
              compare the result with .skills-evals/baseline.json

Mondays 06:00 UTC, or a manual run
        |
        +-- Behavioural evals
              if ANTHROPIC_API_KEY is unset, print a notice and exit 0
              if it is set, run only case files that contain an evals array
              this repository ships neither the secret nor any evals array
```

| Workflow | When | What it does |
| --- | --- | --- |
| `.github/workflows/skills-lint.yml` | pull request, push to `main` | `skill-validator` v1.8.0, strict, no model |
| `.github/workflows/skills-evals.yml` | pull request, push to `main` | `skills-evals` v0.2.0, tiers 1 and 2, no model and no secrets |
| `.github/workflows/skills-behavioral.yml` | Mondays 06:00 UTC, and manual dispatch | behavioural tier, only when `ANTHROPIC_API_KEY` is set |

Every workflow sets `permissions: contents: read`. Third-party actions are pinned to commit SHAs.

The lint job still reports one accepted warning: `ui-design`'s description reads as a keyword list. That line is in `scripts/skills-lint-allowlist.json`. A finding that is not on the list fails the job. An allowlist line the validator stops reporting also fails the job.

Trigger evals pass with three warnings. `html-email-report` and `research-brief-writing` say "Use when" inside a folded YAML block, which skills-evals 0.2.0 does not unfold. `ui-design` has no "Use when" clause. Warnings do not fail the job. Rewriting those descriptions is out of scope: the skill files are copied unchanged.

Details, local commands, and how to add a case are in [docs/skills-ci.md](docs/skills-ci.md).

## Skills in this repo

| Skill | What it is for |
| --- | --- |
| `html-email-report` | Turn a written brief into a Gmail-safe HTML email with a plain-text alternative |
| `research-brief-writing` | Turn sourced notes into a daily or weekly decision brief |
| `unslop` | Edit draft prose to remove model-ish patterns |
| `ui-design` | Design or improve a web or native interface. Apache-2.0 skill; see its `LICENSE` and `NOTICE` |

`html-email-report`, `research-brief-writing`, and `unslop` are covered by the MIT [LICENSE](LICENSE) at the repository root. `ui-design` keeps its own Apache-2.0 license and third-party notices. The root MIT license does not replace that skill's license.

## Reuse this pipeline

1. Copy `.github/workflows/skills-lint.yml`, `.github/workflows/skills-evals.yml`, and `.github/workflows/skills-behavioral.yml`.
2. Copy `scripts/skills-lint.sh`, `scripts/skills_lint_gate.py`, `scripts/skills-lint-allowlist.json`, `skills-evals.config.json`, and `docs/skills-ci.md`.
3. Put each skill at `skills/<name>/SKILL.md`. Keep the workflow permission at `contents: read`.
4. Keep the pinned action SHAs and the skill-validator checksums. Do not switch them to a floating tag or `latest`.
5. Add `evals/cases/<name>.json` with three prompts that should route to the skill and two that should route to another skill in the same repo. See the doc for the shape.
6. Run the linter and `npx --yes skills-evals@0.2.0 run --update-baseline`. Commit `.skills-evals/baseline.json`.
7. Leave `ANTHROPIC_API_KEY` unset unless you intentionally want the weekly behavioural job to call a model. Do not commit the key.

If your skills use a different layout, change the flags in `scripts/skills-lint.sh` and say why in your own doc. This repo allows companion files beside `SKILL.md`, allows `agents/` and `reference/` (used by `ui-design`), and skips orphan checks so license and provenance files are not treated as forgotten references.

## Credits

- [skill-validator](https://github.com/agent-ecosystem/skill-validator) v1.8.0. MIT License, copyright 2026 Dachary Carey. The lint job downloads the Linux release archive and checks it against the checksums published with that release.
- [skills-evals](https://github.com/ahnafyy/skills-evals) v0.2.0, commit `ef618aabbbd4c03cd7ccc44916f91f320eb389ea`. MIT License, copyright 2026 Ahnaf Prio. Docs: <https://ahnafyy.github.io/skills-evals/>.
- [Agent Skills specification](https://github.com/agentskills/agentskills) and <https://agentskills.io>. Code and the specification are Apache License 2.0. Documentation is CC-BY-4.0. See the upstream `LICENSE` and `GOVERNANCE.md`.
- `ui-design` adapts [Impeccable](https://github.com/pbakaus/impeccable) by Paul Bakaus (Apache-2.0). Its iOS notes also carry the MIT notice for [platform-design-skills](https://github.com/ehmo/platform-design-skills). Both notices are in `skills/ui-design/`.
