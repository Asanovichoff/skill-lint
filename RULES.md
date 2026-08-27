# skill-lint rule reference

Every rule, what triggers it, and why it matters.

## Errors — distribution fails until these are fixed

| Code | Rule | Why |
| :--- | :--- | :--- |
| E001 | No `SKILL.md` in the directory | A skill is defined by its `SKILL.md`; without one nothing loads. |
| E002 | Frontmatter missing, unclosed, or not a YAML mapping | The file must open with `---`, hold a YAML mapping, and close with `---`. |
| E003 | Unknown frontmatter key | The key is in neither the spec nor Claude Code's extension set — almost always a typo. |
| E004 | Claude Code-only key, with target `spec` or `both` | claude.ai uploads, the Skills API, and `package_skill.py` reject anything outside the six spec fields with a hard error. |
| E005 | `name` missing, with target `spec` or `both` | The Skills API requires it. Claude Code alone would fall back to the directory name. |
| E006 | `name` longer than 64 characters | Hard limit. |
| E007 | `name` contains an XML tag | Hard limit. |
| E008 | `name` is not lowercase letters, digits, and single hyphens | Hard format requirement. |
| E009 | `name` contains `anthropic` or `claude` | Both words are reserved. |
| E010 | `description` missing or empty | Non-empty is a hard requirement, and it is the only text Claude sees when deciding whether to load the skill. |
| E011 | `description` longer than 1024 characters | Hard limit. |
| E012 | `description` contains an XML tag | Hard limit. |
| E013 | `compatibility` longer than 500 characters | Hard limit. |
| E014 | `metadata` is not a YAML map | A non-map value is dropped rather than read. |
| E015 | Bundle larger than 30 MB uncompressed | Upload limit across all files combined. |

## Warnings — the skill loads, but works less well

| Code | Rule | Why |
| :--- | :--- | :--- |
| W001 | No `name`, target `claude-code` | Works, but the listing label then comes from the directory name. |
| W002 | Vague name (`helper`, `utils`, `tools`, `data`, ...) | Selection degrades once many skills are loaded. |
| W003 | `name` differs from the skill's directory name | The slash command comes from the directory, so the two drifting apart confuses users. |
| W004 | `description` never says when to use the skill | Discovery matches the request against the description. A description with only the what makes Claude guess the when. |
| W005 | `description` in first or second person | Third person is the documented convention and reads consistently against other skills. |
| W006 | `description` under 40 characters | Too short to carry both the what and the when. |
| W007 | `description` restates the name | Adds nothing to selection. |
| W008 | `description` plus `when_to_use` over 1536 characters | Claude Code truncates the pair at that length in the listing. |
| W010 | Frontmatter present, body empty | The body is the whole payload once the skill triggers. |
| W011 | Body over 500 lines | Past that, move reference material into sibling files that load on demand. |
| W012 | Body over roughly 5000 tokens | Every token competes with conversation context once loaded. |
| W013 | Body has no markdown headings | Headings give Claude the structure to follow steps in order. |
| W014 | Backslash paths in the body | Breaks on macOS and Linux. Use forward slashes. |
| W015 | Time-sensitive wording ("as of 2025", "the latest version is") | Goes stale silently and then misleads. |
| W016 | Reference to a file not in the bundle | A dead pointer sends Claude looking for a file that will never load. |
| W017 | Reference chain two levels deep | Keep every reference one level from `SKILL.md` so Claude reads whole files instead of partial ones. |
| W009 | `metadata` reuses a frontmatter field name as a key | Ambiguous for any tooling reading the file. |

## Info

| Code | Rule |
| :--- | :--- |
| I001 | Claude Code-only keys present, target `claude-code`. Fine locally; strip before packaging. |
| I002 | Bundled files never referenced from `SKILL.md`. They ship but never load. |

## The six spec fields

`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.

## Claude Code-only fields

`when_to_use`, `argument-hint`, `arguments`, `disable-model-invocation`,
`user-invocable`, `disallowed-tools`, `model`, `effort`, `context`, `agent`,
`background`, `hooks`, `paths`, `shell`.

## Sources

- Agent Skills overview and best practices, Claude Developer Platform docs
- Skills API guide, Claude Developer Platform docs
- Extend Claude with skills, Claude Code docs (frontmatter reference and
  "Using skill frontmatter outside Claude Code")
