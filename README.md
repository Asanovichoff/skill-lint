# skill-lint

A linter for Agent Skills. Point it at a `SKILL.md` bundle or a repository's
`.claude/skills/` directory and it tells you what will fail on upload, what will
never trigger, and what Claude will read incompletely.

Standard library Python, no dependencies, no API key.

## Why this exists

Agent Skills came out of beta on 19 August 2026: the `/v1/skills` endpoints dropped
their beta header, and sessions now discover skills automatically from a repository's
`.claude/skills/` directory. That combination turns a skills folder into shipping
surface — committed skills load for everyone on the repo, and a bad one is a shipped
defect rather than a local annoyance.

The most common way to ship a bad one is portability. Claude Code accepts twenty
frontmatter fields. The Agent Skills spec accepts six. A skill using
`argument-hint`, `disable-model-invocation`, `model`, `paths` or `hooks` works
perfectly in your repo and then dies at upload with:

```
Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are:
allowed-tools, compatibility, description, license, metadata, name
```

`skill-lint` catches that before you find out from a failed upload.

## Install

As a project skill:

```bash
mkdir -p .claude/skills
cp -r skill-lint .claude/skills/
```

As a personal skill:

```bash
cp -r skill-lint ~/.claude/skills/
```

Then ask Claude to lint your skills, or run `/skill-lint`.

## Use it directly

```bash
# one skill
python3 scripts/lint_skills.py ~/.claude/skills/deploy

# every skill in a repo, as the upload path would see it
python3 scripts/lint_skills.py .claude/skills --target spec --strict

# machine-readable
python3 scripts/lint_skills.py . --json
```

| Flag | Effect |
| :--- | :--- |
| `--target spec` | Only the six spec fields are legal. Use before uploading or packaging. |
| `--target claude-code` | Claude Code's full field set is legal. Use for skills that stay local. |
| `--target both` | Default. Claude Code-only fields are reported as errors. |
| `--strict` | Exit non-zero on warnings as well as errors. |
| `--json` | Structured findings for CI or other tooling. |
| `--quiet` | Drop the summary line. |

Exit codes: `0` clean, `1` findings, `2` bad invocation.

## What it checks

15 error rules covering everything that makes an upload, package, or discovery step
fail outright — missing or unclosed frontmatter, unknown keys, Claude Code-only keys
on a spec target, name format and reserved words, the 64 and 1024 character limits,
the 30 MB bundle cap.

17 warning rules covering everything that makes a skill work badly rather than not at
all — a description that never says *when* to use the skill, first-person phrasing,
vague names, bodies over 500 lines or 5,000 tokens, backslash paths, time-sensitive
wording that goes stale, dead file references, and reference chains more than one
level deep.

`RULES.md` has the full table with the reason behind each rule.

## Sample output

```
portability-break  .claude/skills/portability-break
  ERROR   E004  frontmatter key(s) argument-hint, disable-model-invocation, model work only in Claude Code
          claude.ai upload, the Skills API and package_skill.py reject these with
          'Unexpected key(s) in SKILL.md frontmatter'.
  WARNING W004  description never says WHEN to use the skill
          Add a trigger clause: 'Use when ...' or 'Triggers on ...'.
          5 lines, ~23 tokens, 1 file(s), 0.3 KB
```

## CI

`examples/github-action.yml` lints every skill in a repository on push and pull
request, and writes the JSON findings to the job summary.

## Tests

```bash
bash tests/run_tests.sh
```

Six fixtures, one per failure mode, plus exit-code assertions and a self-lint —
`skill-lint` passes its own `--target spec --strict` run.

## License

MIT
