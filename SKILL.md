---
name: skill-lint
description: Validates Agent Skills (SKILL.md bundles) against the Agent Skills spec, the Skills API upload requirements, and authoring guidance that affects whether Claude triggers the skill. Reports hard errors that make an upload or package fail, portability problems where Claude Code-only frontmatter will be rejected elsewhere, and description or structure issues that hurt skill selection. Use when writing, reviewing, packaging, or publishing a skill, when a skill upload fails, when a skill is not triggering, or when auditing the skills in a repository's .claude/skills directory.
license: MIT
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/lint_skills.py *) Read Glob
---

# skill-lint

Check skill bundles before they ship. The validator is deterministic — run it, read
the findings, fix the file. Do not re-derive the rules by hand.

## Instructions

### 1. Find what to check

If the user named a skill directory, use it. Otherwise look for `.claude/skills/` at
the repository root and in the working directory, and for any directory containing a
`SKILL.md`.

### 2. Run the validator

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/lint_skills.py <path> [<path> ...]
```

Pick the target with `--target`:

| Target        | Use when                                                                 |
| :------------ | :----------------------------------------------------------------------- |
| `spec`        | The skill will be uploaded to claude.ai, sent to the Skills API, or packaged |
| `claude-code` | The skill lives in `.claude/skills/` and stays local                     |
| `both`        | Default. Reports portability problems as errors                          |

Add `--json` when the output feeds other tooling, `--strict` to fail the run on
warnings as well as errors, and `--quiet` to drop the summary line.

Exit codes: `0` clean, `1` findings, `2` bad invocation.

### 3. Report and fix

Work through findings in this order, because the first group blocks distribution
outright:

1. `E0xx` errors — the upload, package, or discovery step fails until these are fixed.
2. `W0xx` warnings — the skill loads but Claude is less likely to pick it, or reads
   incomplete material.
3. `I0xx` info — worth mentioning, not worth blocking on.

For each error, state the rule and the fix rather than only the code. `RULES.md` in
this skill directory carries the full rule table with the reason behind each check;
read it when a finding needs explaining or when the user disputes one.

### 4. Re-run

After editing, run the validator again. Repeat until the target exit code is `0`.
Never report a skill as clean without a passing run.

## The portability rule this exists for

Claude Code accepts far more frontmatter than the Agent Skills spec does. Anything
outside `name`, `description`, `license`, `compatibility`, `metadata`, and
`allowed-tools` works locally and then fails at upload or packaging with:

```
Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are:
allowed-tools, compatibility, description, license, metadata, name
```

A skill that works in your repo can be undistributable for this reason alone, which
is why `--target both` treats a Claude Code-only key as an error.

## Wiring it into CI

`examples/github-action.yml` in this skill directory is a ready workflow that lints
every skill in a repository on each push. Suggest it when a repository has more than
one skill or when skills are shared across a team.

## Examples

Lint one skill, strictly, before uploading it:

```bash
python3 scripts/lint_skills.py ~/.claude/skills/deploy --target spec --strict
```

Audit every skill in a repository and machine-read the result:

```bash
python3 scripts/lint_skills.py . --json
```
